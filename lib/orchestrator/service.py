"""唯一 PipelineOrchestrator（Phase 3）—— WebUI / CLI / Hermes 共用的执行内核。

设计要点
  1. 入口唯一：三条入口都只调 `start()` / `resume()` / `cancel()` / `retry()`，
     任务的 DB 结构（jobs + attempts + artifacts + events）因此完全一致；
  2. 事实源唯一：状态只经 `JobStore.transition()`，进度只经 JobStore event stream，
     不再有"轮询脚本字符串猜阶段"的第二套逻辑；
  3. 并发受控：job 级线程池上限 = `gen_concurrency`，真正限制同时在跑的出片数；
  4. 取消是协作式的：`CANCEL_REQUESTED` 事件 + kill 当前子进程树 → job 明确进入
     `CANCELLED`，不留孤儿子进程；
  5. 进程重启后 `recover_interrupted()` 把遗留的"运行中"任务收敛为 `PAUSED`，
     查询与恢复都不依赖内存态。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from .. import STATE_DIR
from ..creative import CreativePlanner
from ..creative.planner import PlannerError
from ..dispatch import sync_queue
from ..jobstore import InvalidTransition, JobState, can_transition, sha256_of
from ..jobstore import store as default_store
from . import repairs as repairs_mod
from . import stages as stages_mod
from .errors import (
    REQUIRE_HUMAN,
    UNEXPECTED_ERROR,
    WAIT_AND_RESUME,
    BudgetExceeded,
    Cancelled,
    OrchestratorError,
    StageFailure,
    UnknownJob,
)
from .models import (
    FRONTEND_STAGE,
    INTERRUPTIBLE_STATES,
    STAGE_LABEL,
    STAGE_ORDER,
    STAGE_STATES,
    RunConfig,
    StageContext,
    StageResult,
)
from .policies import policy_for
from .recovery import RepairEngine, recover_interrupted

QUEUE_DIR = STATE_DIR / "queue_15s"
CONSOLE_STATE_FILE = STATE_DIR / "console.json"

DEFAULT_CONSOLE = {
    "daily_target": 1, "gen_concurrency": 6, "dry_mode": False,
    "real_publish": False, "real_engage": False, "publish_platforms": ["douyin"],
}


def console_state() -> dict:
    """读 WebUI 设置（state/console.json）；CLI / Hermes 与 WebUI 共用同一份用户意图。"""
    state = dict(DEFAULT_CONSOLE)
    try:
        if CONSOLE_STATE_FILE.exists():
            data = json.loads(CONSOLE_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state.update(data)
    except (OSError, ValueError):
        pass
    state.pop("mode", None)
    return state


def kill_process_tree(pid: int) -> bool:
    """按进程树杀子进程（Windows 用 taskkill /T，其他平台 SIGTERM 进程组）。"""
    try:
        if sys.platform == "win32":
            done = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                  capture_output=True, timeout=20)
            return done.returncode == 0
        import os
        import signal
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True
    except Exception:
        with suppress(Exception):
            import os
            os.kill(pid, 9)
            return True
        return False


class _RunHandle:
    """一个正在执行的 job（可取消、可观察，持有当前子进程句柄）。"""

    def __init__(self, uid: str, run_id: str = "") -> None:
        self.uid = uid
        self.run_id = run_id
        self.cancel = threading.Event()
        self.stage = ""
        self.started = time.time()
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    @property
    def cancelled(self) -> bool:
        return self.cancel.is_set()

    @property
    def proc(self) -> subprocess.Popen | None:
        with self._lock:
            return self._proc

    def register_proc(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._proc = proc

    def clear_proc(self, proc: subprocess.Popen | None = None) -> None:
        with self._lock:
            if proc is None or self._proc is proc:
                self._proc = None

    def kill_proc(self) -> bool:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return False
        return kill_process_tree(proc.pid)


class PipelineOrchestrator:
    """唯一执行内核。进程内单例 `orchestrator` 见模块底部。"""

    def __init__(self, *, store=None, stages=None, queue_dir=None, root=None,
                 repair: RepairEngine | None = None, provider=None,
                 sleep=None, poll_interval: float = 20.0, max_wait: float = 1800.0,
                 download_retries: int = 3) -> None:
        self.store = store or default_store
        self.stages = dict(stages) if stages is not None else stages_mod.default_stages()
        self.repair = repair or RepairEngine()
        self.provider = provider          # 供应商适配器（None = 由 stage 懒加载真实的 AutoDL）
        self.root = Path(root) if root else Path(__file__).resolve().parent.parent.parent
        self.queue_dir = Path(queue_dir) if queue_dir else QUEUE_DIR
        self._handles: dict[str, _RunHandle] = {}
        self._futures: dict[str, Future] = {}
        self._lock = threading.RLock()
        self._pool: ThreadPoolExecutor | None = None
        self._sleep = sleep or time.sleep
        self.poll_interval = poll_interval
        self.max_wait = max_wait
        self.download_retries = download_retries
        self._pool_size = 0
        self._pending = 0
        self._last_run: dict = {}

    # ── 启动 ───────────────────────────────────────────────────
    def start(self, config: RunConfig | None = None, *, goal: str = "",
              count: int | None = None, source: str = "cli",
              specs: list[str | Path] | None = None,
              background: bool = True) -> dict:
        """创建 N（=daily_target 或 count）个 job 并开始执行。"""
        cfg = config or RunConfig(goal=goal, source=source)
        cfg.goal = cfg.goal or goal
        cfg.source = cfg.source or source

        try:
            items, info = self._plan_batch(cfg, specs=specs, count=count)
        except PlannerError as exc:
            # 规划失败必须在**创建任何任务之前**收口：不进付费阶段，不留下半成品 job
            return {"ok": False, "jobs": [], "count": 0, "error_code": "PLAN_FAILED",
                    "error": f"自主规划失败：{exc}",
                    "message": "规划未通过，未创建任何任务（更未进入付费生成）"}
        if not items:
            if info.get("up_to_date"):
                return {"ok": True, "jobs": [], "count": 0, "skipped": [],
                        "dry": cfg.dry_mode, "source": cfg.source,
                        "message": f"今日 daily_target={info.get('daily_target')} 已补齐，"
                                   "没有需要新建的任务"}
            return {"ok": False, "jobs": [], "count": 0, "error_code": "NO_SPEC",
                    "error": "没有需要生产的任务：今日 daily_target 已补齐，"
                             "或把 spec 放进 state/queue_15s/ 手动指定选题"}

        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot = cfg.to_dict()
        serialized = json.dumps(snapshot, ensure_ascii=False)
        uids: list[str] = []
        skipped: list[str] = []
        for item in items:
            uid = item["uid"]
            existing = self.store.get_job(uid)
            if existing is None:
                self.store.create_job(goal=item.get("goal") or cfg.goal, uid=uid,
                                      fingerprint=item.get("fingerprint"),
                                      config_snapshot=snapshot, budget_cap=cfg.budget_cap)
                if item.get("spec"):
                    self.store.add_artifact(uid, "spec", item["spec"], stage="planning")
            else:
                if existing.get("status") in (JobState.READY, JobState.DONE, JobState.CANCELLED):
                    skipped.append(uid)      # 已出过片，不重复生产（要重跑用 retry/resume）
                    continue
                if existing.get("config_snapshot") != serialized:
                    # 必须真的落库：resume/retry 只从 job.config_snapshot 还原这次运行
                    self.store.set_fields(uid, config_snapshot=serialized)
                    self.store.add_event(uid, "config_updated",
                                         "本次运行的配置快照与历史不同（已按新配置执行）")
                fp = item.get("fingerprint")
                if fp and existing.get("fingerprint") != fp:
                    self.store.set_fields(uid, fingerprint=fp)
            uids.append(uid)

        if not uids:
            return {"ok": True, "run_id": run_id, "jobs": [], "count": 0, "skipped": skipped,
                    "dry": cfg.dry_mode, "source": cfg.source, "config": snapshot,
                    "message": f"队列里 {len(skipped)} 条任务已完成，没有新任务"}
        with self._lock:
            self._last_run = {
                "run_id": run_id, "uids": list(uids), "total": len(uids), "finished": 0,
                "failed": 0, "cancelled": 0, "stages": list(cfg.stages),
                "source": cfg.source, "dry": cfg.dry_mode,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": None, "ok": None,
            }
        if background:
            self._submit(uids, cfg)
        else:
            for uid in uids:
                self._execute(uid, cfg)
            self._close_run()
        return {"ok": True, "run_id": run_id, "jobs": uids, "count": len(uids),
                "dry": cfg.dry_mode, "source": cfg.source, "config": snapshot,
                "message": f"已启动生产：{len(uids)} 条"
                           + ("（演练模式）" if cfg.dry_mode else "")}

    def _plan_batch(self, cfg: RunConfig, *, specs, count) -> tuple[list[dict], dict]:
        """算出这一批要跑哪些 job：(items, info)。info 说明"为什么是这些"。"""
        target = max(1, int(count if count is not None else cfg.daily_target))
        items: list[dict] = []
        if specs:
            for raw in specs:
                p = Path(raw)
                items.append({"uid": p.stem, "spec": p, "goal": cfg.goal,
                              "fingerprint": _fingerprint(p)})
            return items[:target], {"explicit": True, "daily_target": target}

        registered = sync_queue(self.queue_dir, store=self.store)
        for uid, path in sorted(registered.items()):
            p = Path(path)
            items.append({"uid": uid, "spec": p, "goal": cfg.goal,
                          "fingerprint": _fingerprint(p)})
        items = items[:target]
        if len(items) >= target:
            return items, {"queued": len(registered), "daily_target": target}

        # Phase 5：队列里没有现成 spec 时，系统自己选题（不再依赖人工塞 spec）。
        #   队列为空 → 按"daily_target - 今日已存在/已完成"补齐（计划 §Phase 5 任务 1）；
        #   队列已有料 → 只补这一批的缺口（用户手工投料的语义保持不变）。
        if cfg.dry_mode:
            # 演练免费但**不落盘**：保持 Phase 3 的"虚拟 spec"口径，避免演练污染队列
            items += [self._placeholder(cfg, i) for i in range(len(items), target)]
            return items, {"dry_placeholder": True, "daily_target": target}

        planner = CreativePlanner(store=self.store, queue_dir=self.queue_dir,
                                  state_dir=self.queue_dir.parent)
        need = (planner.needed(target) if not registered
                else max(0, target - len(items)))
        if need <= 0:
            return items, {"up_to_date": True, "daily_target": target,
                           "today": planner.active_or_completed_today()}
        for planned in planner.plan_batch(need, goal=cfg.goal):
            items.append({"uid": planned.uid, "spec": planned.spec_path,
                          "goal": planned.dna.hotspot or cfg.goal,
                          "fingerprint": _fingerprint(planned.spec_path)})
        return items, {"auto_planned": len(items), "daily_target": target}

    def _placeholder(self, cfg: RunConfig, index: int) -> dict:
        day = datetime.now().strftime("%Y%m%d")
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "", cfg.goal or "")[:16] or "auto"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"job_{day}_{slug}_{stamp}_{index + 1:02d}"
        uid = base
        n = 1
        while self.store.get_job(uid) is not None:   # 同一秒内多次启动也要各不相同
            n += 1
            uid = f"{base}_{n}"
        return {"uid": uid, "spec": None, "goal": cfg.goal,
                "fingerprint": sha256_of(f"{cfg.goal}|{index}|{uid}".encode())}

    def _submit(self, uids: list[str], cfg: RunConfig, *, from_stage: str | None = None) -> None:
        with self._lock:
            if self._pool is None or self._pool_size != cfg.gen_concurrency:
                if self._pool is not None:
                    self._pool.shutdown(wait=False)
                self._pool = ThreadPoolExecutor(max_workers=cfg.gen_concurrency,
                                                thread_name_prefix="orch")
                self._pool_size = cfg.gen_concurrency
            self._pending += len(uids)
            for uid in uids:
                self._futures[uid] = self._pool.submit(self._execute, uid, cfg, from_stage)

    # ── 执行 ───────────────────────────────────────────────────
    def _execute(self, uid: str, cfg: RunConfig, from_stage: str | None = None):
        handle = _RunHandle(uid, self._last_run.get("run_id", ""))
        with self._lock:
            self._handles[uid] = handle
        result = None
        try:
            result = self._run_stages(uid, cfg, handle, from_stage=from_stage)
            with self._lock:
                if self._last_run:
                    self._last_run["finished"] = int(self._last_run.get("finished") or 0) + 1
            if not cfg.dry_mode:
                self._archive_spec(uid)      # 出片成功 → spec 移入 queue/_done，队列不留已出片的条目
        except Cancelled as exc:
            self._finalize_cancel(uid, exc)
        except OrchestratorError as exc:
            self._finalize_failure(uid, exc)
        except Exception as exc:  # 兜底：绝不让 job 卡在"运行中"
            self._finalize_failure(uid, StageFailure(str(exc), error_code=UNEXPECTED_ERROR))
        finally:
            handle.kill_proc()
            with self._lock:
                self._handles.pop(uid, None)
                self._pending = max(0, self._pending - 1)
                if self._pending == 0 and self._pool is not None:
                    self._pool.shutdown(wait=False)
                    self._pool = None
                    self._pool_size = 0
                self._close_run()
        return result

    def _run_stages(self, uid: str, cfg: RunConfig, handle: _RunHandle,
                    *, from_stage: str | None = None) -> StageResult:
        """顺序跑阶段，并支持**定点修复回退**（Phase 8）。

        某个阶段报 FAIL 且修复动作指向别的阶段（重生 / 只重建字幕）时，不原地空转，
        而是走 REPAIRING 回退到目标阶段重做 —— 次数受 `cfg.max_repairs` 限制，
        到顶即转人工（BLOCKED），绝不死循环。
        """
        job = self.store.get_job(uid)
        if job is None:
            raise UnknownJob(f"任务不存在：{uid}")
        all_stages = list(stages_mod.resolve_stages(cfg.stages))
        stages = list(all_stages)
        if from_stage in stages:
            stages = stages[stages.index(from_stage):]

        limit = max(0, int(getattr(cfg, "max_repairs", 0) or 0))
        repairs = self._repairs_used(uid)
        last: StageResult | None = None
        pending: dict | None = None          # 最近一次"已计划但成本未知"的修复
        idx = 0
        while idx < len(stages):
            name = stages[idx]
            if handle.cancelled:
                raise Cancelled("收到取消请求，安全停止")
            if not cfg.dry_mode:
                self._ensure_budget(uid, cfg, name)
            fn = self.stages.get(name)
            if fn is None:
                raise StageFailure(f"未注册的 stage：{name}", error_code="STAGE_NOT_REGISTERED")
            self._walk_to(uid, STAGE_STATES[name][0], message=f"{STAGE_LABEL[name]}开始")
            self.store.add_event(uid, "stage_start", f"▶ {STAGE_LABEL[name]}", stage=name)
            try:
                last = self._run_one_stage(uid, cfg, handle, name, fn)
            except StageFailure as exc:
                plans = (exc.data or {}).get("repair_plan") or {}
                target = str(plans.get("rewind_to") or "")
                # 断点续跑可能把更早的 stage 截掉了；回退目标只要在本配置里就补回来
                if target and target in all_stages and target not in stages:
                    stages = list(all_stages)
                # 需要回退才算"定点修复"；就地重跑由 _run_one_stage 内部消化
                if not target or target not in stages or target == name:
                    self._finalize_repair(uid, pending, status="FAILED",
                                          error_code=exc.error_code or "")
                    raise
                if repairs >= limit:
                    self._finalize_repair(uid, pending, status="FAILED",
                                          error_code=exc.error_code or "")
                    raise StageFailure(
                        f"定点修复已达上限 {limit} 次（{exc.error_code}）：{exc.message}",
                        error_code=exc.error_code,
                        data={**(exc.data or {}), "repairs_used": repairs,
                              "repairs_limit": limit, "repair_exhausted": True},
                        next_action=REQUIRE_HUMAN) from exc
                # 上一次修复的口子在这次失败处结束 → 结算它的真实成本/结果
                self._finalize_repair(uid, pending, status="EXECUTED")
                repairs += 1
                job = self.store.get_job(uid) or {}
                repair_id = self._record_repair(uid, plans, repairs, limit)
                pending = {"id": repair_id, "error_code": plans.get("error_code"),
                           "stage": plans.get("stage") or name,
                           "cost0": float(job.get("cost_spent") or 0.0)}
                self._try_transition(uid, JobState.REPAIRING, message="进入定点修复",
                                     event_type="repair_begin", data={"rewind_to": target})
                idx = stages.index(target)
                continue
            idx += 1
        self._finalize_repair(uid, pending, status="EXECUTED")
        return last or StageResult.ok("plan", message="无阶段可执行")

    def _repairs_used(self, uid: str) -> int:
        """已经用掉的修复次数（读 DB，因此 resume/retry 也接着算，不会靠内存绕过预算）。"""
        with suppress(Exception):
            return int(self.store.repair_summary(uid).get("count") or 0)
        return 0

    def _record_repair(self, uid: str, plan: dict, used: int, limit: int) -> int | None:
        """落一条修复记录（次数此刻可知；真实成本等重跑完由 `_finalize_repair` 回填）。"""
        detail = {**plan, "used": used, "limit": limit}
        repair_id = None
        with suppress(Exception):
            repair_id = self.store.add_repair(
                uid, error_code=str(plan.get("error_code") or "UNKNOWN"),
                action=str(plan.get("action") or ""),
                stage=str(plan.get("stage") or ""),
                rewind_to=str(plan.get("rewind_to") or ""),
                target_shot=plan.get("target_shot"), attempt=used,
                budget=limit, cost=0.0, status="PLANNED", detail=detail)
        with suppress(Exception):
            self.store.add_event(uid, "repair", f"↺ 定点修复 {used}/{limit}",
                                 stage=str(plan.get("stage") or ""),
                                 data={"repair_plan": plan, "used": used, "limit": limit})
        self._log(f"  ↺ {uid} 定点修复 {used}/{limit}：{plan.get('error_code')} → "
                  f"{plan.get('action')}（回退到 {plan.get('rewind_to') or plan.get('stage')}）")
        return repair_id

    def _finalize_repair(self, uid: str, pending: dict | None, *, status: str,
                         error_code: str = "") -> None:
        """回填一次修复的**真实成本与结果**（PLANNED → EXECUTED / FAILED）。"""
        if not pending:
            return
        job = self.store.get_job(uid) or {}
        spent = float(job.get("cost_spent") or 0.0)
        cost = round(max(0.0, spent - float(pending.get("cost0") or 0.0)), 4)
        detail = {"repair_id": pending.get("id"), "repair_error": pending.get("error_code"),
                  "status": status, "error_code": error_code or None, "cost": cost}
        with suppress(Exception):
            self.store.update_repair(pending.get("id"), cost=cost, status=status, detail=detail)
        with suppress(Exception):
            self.store.add_event(uid, "repair_done",
                                 f"↺ 定点修复 {pending.get('error_code')} → {status}"
                                 f"（¥{cost:.2f}）", stage=str(pending.get("stage") or ""),
                                 data=detail)

    def _run_one_stage(self, uid: str, cfg: RunConfig, handle: _RunHandle,
                       name: str, fn) -> StageResult:
        attempt = 0
        while True:
            attempt += 1
            if handle.cancelled:
                raise Cancelled("收到取消请求，安全停止")
            handle.stage = name
            ctx = StageContext(uid=uid, stage=name, spec=self._spec_path(uid),
                               job=self.store.get_job(uid) or {}, config=cfg,
                               workspace=self._workspace(uid), root=self.root,
                               queue_dir=self.queue_dir, state_dir=self.queue_dir.parent,
                               store=self.store, provider=self.provider,
                               handle=handle, log=self._log, sleep=self._sleep,
                               poll_interval=self.poll_interval,
                               max_wait=self.max_wait,
                               download_retries=self.download_retries)
            attempt_id = self.store.record_attempt(uid, name, attempt_no=attempt)
            t0 = time.time()
            try:
                result = fn(ctx)
            except Cancelled:
                self.store.finish_attempt(attempt_id, "CANCELLED",
                                          error_code="CANCEL_REQUESTED", message="取消")
                raise
            except Exception as exc:
                result = StageResult.fail(name, UNEXPECTED_ERROR,
                                          f"{type(exc).__name__}: {exc}")
            seconds = round(time.time() - t0, 1)
            cost = result.cost
            self.store.finish_attempt(
                attempt_id, "SUCCESS" if result.success else (result.error_code or "FAILED"),
                error_code=None if result.success else result.error_code,
                cost=cost, message=result.message[:500])
            if cost:
                self.store.add_cost(uid, cost)
            for art in result.artifacts:
                self._record_artifact(uid, name, art)
            if result.success:
                self.store.add_event(
                    uid, "stage_end", f"✓ {STAGE_LABEL[name]}：{result.message}", stage=name,
                    data={"metrics": result.metrics, "seconds": seconds, "attempt": attempt})
                self._walk_to(uid, STAGE_STATES[name][-1])
                return result

            policy = policy_for(name)
            decision = self.repair.decide(result, attempts=attempt,
                                          max_attempts=cfg.max_attempts, stage=name)
            target = repairs_mod.repair_target(decision.action, name)
            rewind = bool(decision.in_stage and target and target != name)
            plan = repairs_mod.plan_repair(
                result.error_code or "UNKNOWN", stage=name, attempt=attempt,
                budget=int(getattr(cfg, "max_repairs", 0) or 0),
                findings=(result.data or {}).get("findings"),
                detail={"message": result.message, "rewind_to": target}) if rewind else None
            self.store.add_event(
                uid, "stage_failed", f"✗ {STAGE_LABEL[name]}：{result.message}", stage=name,
                data={"error_code": result.error_code, "decision": decision.action,
                      "reason": decision.reason, "repair": decision.to_dict(),
                      "repair_plan": plan.to_dict() if plan else None,
                      "metrics": result.metrics,
                      "seconds": seconds, "attempt": attempt, "detail": result.data})
            if decision.in_stage and not rewind and attempt < policy.max_attempts:
                if decision.delay:
                    self._log(f"  ⏳ {uid} {name} 瞬时错误（{result.error_code}）"
                              f"→ 退避 {decision.delay:.0f}s 后重试")
                    self._sleep(decision.delay)
                self._log(f"  ↻ {uid} {name} 第 {attempt} 次失败"
                          f"（{result.error_code}）→ {decision.action}")
                continue
            raise StageFailure(result.message, error_code=result.error_code or "STAGE_FAILED",
                               data={**result.data, "repair_action": decision.action,
                                     "repair_reason": decision.reason,
                                     "repair_plan": plan.to_dict() if plan else None},
                               next_action=decision.action)

    def _ensure_budget(self, uid: str, cfg: RunConfig, stage: str = "") -> None:
        """双层预算保护：整条 job 的 budget_cap + 单阶段的 max_cost（预估即拦）。

        必须在**付费前**调用 —— 一旦钱花出去才发现超预算就已经晚了。
        """
        job = self.store.get_job(uid) or {}
        spent = float(job.get("cost_spent") or 0.0)
        cap = cfg.budget_cap if cfg.budget_cap is not None else job.get("budget_cap")
        if cap is None:
            return
        cap = float(cap)
        if spent >= cap:
            raise BudgetExceeded(f"预算已用尽：已花 ¥{spent:.2f} ≥ 上限 ¥{cap:.2f}",
                                 data={"spent": spent, "budget_cap": cap, "stage": stage})
        policy = policy_for(stage) if stage else None
        reserve = float(policy.max_cost or 0.0) if policy is not None else 0.0
        if reserve and spent + reserve > cap:
            raise BudgetExceeded(
                f"预算不足以支付「{stage}」（已花 ¥{spent:.2f} + 本阶段上限 "
                f"¥{reserve:.2f} > 总预算 ¥{cap:.2f}）→ 付费前拦停",
                data={"spent": spent, "reserve": reserve, "budget_cap": cap, "stage": stage})

    # ── resume / retry / cancel ────────────────────────────────
    def resume(self, uid: str, *, background: bool = True) -> dict:
        job = self.store.get_job(uid)
        if job is None:
            return {"ok": False, "error_code": "UNKNOWN_JOB", "error": f"任务不存在：{uid}"}
        if job["status"] in JobState.TERMINAL:
            return {"ok": False, "error_code": "JOB_NOT_RESUMABLE",
                    "error": f"任务已终结（{job['status']}），不可恢复"}
        return self._rerun(uid, job, event="resume", background=background,
                           message="从断点继续")

    def retry(self, uid: str, *, background: bool = True) -> dict:
        job = self.store.get_job(uid)
        if job is None:
            return {"ok": False, "error_code": "UNKNOWN_JOB", "error": f"任务不存在：{uid}"}
        if job["status"] not in (JobState.FAILED, JobState.BLOCKED):
            return {"ok": False, "error_code": "JOB_NOT_RESUMABLE",
                    "error": f"只有 FAILED/BLOCKED 的任务可重试（当前 {job['status']}）"}
        return self._rerun(uid, job, event="retry", background=background, message="重试",
                           clear_error=True)

    def _rerun(self, uid: str, job: dict, *, event: str, background: bool,
               message: str, clear_error: bool = False) -> dict:
        cfg = self._config_from_job(job)
        stage = self._resume_stage(job, cfg)
        if clear_error:
            with suppress(Exception):
                self.store.set_fields(uid, error_code=None)
        self.store.add_event(uid, event, f"{message}：{STAGE_LABEL[stage]}", stage=stage,
                             data={"from_status": job["status"], "from_stage": stage})
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with self._lock:
            self._last_run = {
                "run_id": run_id, "uids": [uid], "total": 1, "finished": 0, "failed": 0,
                "cancelled": 0, "stages": list(cfg.stages), "source": cfg.source,
                "dry": cfg.dry_mode, "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": None, "ok": None,
            }
        if background:
            self._submit([uid], cfg, from_stage=stage)
        else:
            self._execute(uid, cfg, stage)
            self._close_run()
        return {"ok": True, "uid": uid, "run_id": run_id, "from_stage": stage,
                "config": cfg.to_dict()}

    def _config_from_job(self, job: dict) -> RunConfig:
        snapshot = job.get("config_snapshot")
        data = {}
        if snapshot:
            with suppress(TypeError, ValueError):
                data = json.loads(snapshot) if isinstance(snapshot, str) else dict(snapshot)
        cfg = RunConfig(**{k: v for k, v in data.items() if k in RunConfig.__dataclass_fields__})
        cfg.source = cfg.source or "resume"
        return cfg

    def _resume_stage(self, job: dict, cfg: RunConfig) -> str:
        stages = list(stages_mod.resolve_stages(cfg.stages))
        status = job.get("status")
        if status in JobState.LINEAR:
            for name in stages:
                if status in STAGE_STATES[name]:
                    return name
            return stages[0]
        last_linear = JobState.PLANNING
        with suppress(Exception):
            for e in self.store.list_events(job["uid"]):
                if e.get("to_status") in JobState.LINEAR:
                    last_linear = e["to_status"]
        for name in stages:
            if last_linear in STAGE_STATES[name]:
                return name
        return stages[0]

    def cancel(self, uid: str | None = None, *, all: bool = False,
               reason: str = "") -> dict:
        """协作式取消：记 CANCEL_REQUESTED → 安全终止子进程 → job 进 CANCELLED。"""
        if all or uid is None:
            with self._lock:
                targets = list(self._handles)
            with suppress(Exception):
                for job in self.store.list_jobs(limit=500):
                    # 只收正在跑的任务（PLANNING/READY/DONE 不动：还没开始 / 已经在等发布）
                    if job["status"] in INTERRUPTIBLE_STATES and job["uid"] not in targets:
                        targets.append(job["uid"])
        else:
            targets = [uid]
        cancelled: list[str] = []
        for target in targets:
            if self.cancel_one(target, reason=reason).get("ok"):
                cancelled.append(target)
        return {"ok": True, "cancelled": cancelled, "count": len(cancelled)}

    def cancel_one(self, uid: str, *, reason: str = "") -> dict:
        job = self.store.get_job(uid)
        if job is None:
            return {"ok": False, "error_code": "UNKNOWN_JOB", "error": f"任务不存在：{uid}"}
        if job["status"] in JobState.TERMINAL:
            return {"ok": False, "error_code": "JOB_NOT_RESUMABLE",
                    "error": f"任务已终结（{job['status']}）"}
        handle = self._handles.get(uid)
        self.store.add_event(uid, "cancel_requested", reason or "收到取消请求",
                             stage=handle.stage if handle else None,
                             data={"mode": "cooperative" if handle else "immediate"})
        if handle is not None:
            handle.cancel.set()
            handle.kill_proc()
            return {"ok": True, "uid": uid, "requested": True, "mode": "cooperative"}
        self._try_transition(uid, JobState.CANCELLED, message=reason or "取消（无活动执行）",
                             event_type="cancelled")
        return {"ok": True, "uid": uid, "requested": False, "mode": "immediate"}

    def recover_interrupted(self, *, reason: str = "进程重启，任务被打断") -> list[str]:
        with self._lock:
            active = list(self._handles)
        return recover_interrupted(self.store, active_uids=active, reason=reason)

    def wait(self, timeout: float | None = None, uids: list[str] | None = None) -> dict:
        with self._lock:
            futures = [f for u, f in self._futures.items() if uids is None or u in uids]
        if futures:
            futures_wait(futures, timeout=timeout)
        with self._lock:
            self._futures = {u: f for u, f in self._futures.items() if not f.done()}
            if not self._futures:
                self._close_run()
        return self.status()

    # ── 状态（事实源 = JobStore）───────────────────────────────
    def status(self) -> dict:
        with self._lock:
            handles = list(self._handles.values())
            last = dict(self._last_run)
        total = int(last.get("total") or 0)
        finished = int(last.get("finished") or 0)
        stages = list(last.get("stages") or STAGE_ORDER)
        running = bool(handles)
        progress = 0.0
        current_stage = None
        stage = None
        lead = max(handles, key=lambda h: h.started) if handles else None
        if running and total:
            frac = 0.0
            for handle in handles:
                idx = stages.index(handle.stage) if handle.stage in stages else 0
                frac = max(frac, (idx + 1) / max(1, len(stages)))
            progress = min(99.0, (finished + frac) / total * 100)
            stage = lead.stage
            current_stage = FRONTEND_STAGE.get(lead.stage)
        if running and lead is not None:
            message = f"出片 {lead.uid}（{min(finished + 1, total)}/{total}）· {STAGE_LABEL.get(stage, '')}"
        elif last and total and finished + int(last.get("failed") or 0) + int(last.get("cancelled") or 0) >= total:
            failed = int(last.get("failed") or 0)
            cancelled = int(last.get("cancelled") or 0)
            progress = 100.0
            if failed:
                message = f"失败 {failed} 条"
            elif cancelled:
                message = f"已取消 {cancelled} 条"
            else:
                message = "完成"
            current_stage = stages[-1] if stages else None
            current_stage = FRONTEND_STAGE.get(current_stage) if current_stage else None
        else:
            message = "就绪"
        return {
            "running": running, "current_stage": current_stage, "stage": stage,
            "progress": round(progress, 1), "message": message,
            "active": [h.uid for h in handles], "total": total, "finished": finished,
            "failed": int(last.get("failed") or 0), "cancelled": int(last.get("cancelled") or 0),
            "run_id": last.get("run_id"), "source": last.get("source"),
            "dry": bool(last.get("dry")), "source_of_truth": "jobstore",
            "jobs_by_status": self._counts().get("by_status", {}),
        }

    def _counts(self) -> dict:
        with suppress(Exception):
            return self.store.counts()
        return {}

    # ── 内部工具 ───────────────────────────────────────────────
    def _walk_to(self, uid: str, target: str, *, message: str = "") -> None:
        job = self.store.get_job(uid)
        if job is None:
            raise UnknownJob(f"任务不存在：{uid}")
        cur = job["status"]
        if cur == target:
            return
        if can_transition(cur, target):
            self.store.transition(uid, target, message=message, stage=target.lower())
            return
        if cur in JobState.SIDE:
            cur = JobState.LINEAR[0]
        i = JobState.LINEAR.index(cur) if cur in JobState.LINEAR else 0
        j = JobState.LINEAR.index(target)
        if j < i:
            raise InvalidTransition(f"不能倒退：{cur} → {target}")
        for name in JobState.LINEAR[i + 1:j + 1]:
            self.store.transition(uid, name, message=message if name == target else "",
                                  stage=name.lower())

    def _try_transition(self, uid: str, target: str, *, message: str = "",
                        event_type: str = "status_change", error_code: str | None = None,
                        data: dict | None = None) -> bool:
        try:
            self.store.transition(uid, target, message=message, event_type=event_type,
                                  error_code=error_code, data=data)
            return True
        except InvalidTransition:
            with suppress(Exception):
                self.store.transition(uid, target, message=message, event_type=event_type,
                                      error_code=error_code, data=data, force=True)
                return True
        except (KeyError, ValueError):
            return False
        return False

    def _finalize_failure(self, uid: str, exc: OrchestratorError) -> None:
        code = getattr(exc, "error_code", UNEXPECTED_ERROR)
        job = self.store.get_job(uid) or {}
        action = getattr(exc, "next_action", "") or ""
        # RepairEngine 的收尾语义：等窗口 → PAUSED；交人工 → BLOCKED；其余 → FAILED
        if code in ("BLOCKED_BUDGET", "CAPABILITY_BLOCKED") or action == REQUIRE_HUMAN:
            target = JobState.BLOCKED
        elif action == WAIT_AND_RESUME:
            target = JobState.PAUSED
        else:
            target = JobState.FAILED
        if job.get("status") not in JobState.TERMINAL:
            self._try_transition(uid, target, message=exc.message, event_type="stage_failed",
                                 error_code=code, data=exc.data)
        self._log(f"  ✗ {uid} {target}（{code}）：{exc.message}")
        with self._lock:
            if self._last_run:
                self._last_run["failed"] = int(self._last_run.get("failed") or 0) + 1

    def _finalize_cancel(self, uid: str, exc: Cancelled) -> None:
        job = self.store.get_job(uid) or {}
        if job.get("status") not in JobState.TERMINAL:
            self._try_transition(uid, JobState.CANCELLED,
                                 message="已取消（协作式取消，子进程已安全终止）",
                                 event_type="cancelled", data=exc.data)
        self._log(f"  ⊘ {uid} 已取消")
        with self._lock:
            if self._last_run:
                self._last_run["cancelled"] = int(self._last_run.get("cancelled") or 0) + 1

    def _close_run(self) -> None:
        with self._lock:
            if not self._last_run or self._last_run.get("finished_at"):
                return
            last = self._last_run
            done = int(last.get("finished") or 0) + int(last.get("failed") or 0) \
                + int(last.get("cancelled") or 0)
            if done < int(last.get("total") or 0):
                return
            last["finished_at"] = datetime.now().isoformat(timespec="seconds")
            last["ok"] = not last.get("failed") and not last.get("cancelled")

    def _spec_path(self, uid: str) -> Path | None:
        for art in reversed(self.store.list_artifacts(uid, "spec")):
            path = art.get("path")
            if path and Path(path).is_file():
                return Path(path)
        candidate = self.queue_dir / f"{uid}.json"
        return candidate if candidate.is_file() else None

    def _archive_spec(self, uid: str) -> None:
        spec = self._spec_path(uid)
        if spec is None or spec.parent != self.queue_dir:
            return
        done_dir = self.queue_dir / "_done"
        with suppress(OSError):
            done_dir.mkdir(parents=True, exist_ok=True)
            target = done_dir / spec.name
            if target.exists():
                target = done_dir / f"{spec.stem}_{datetime.now().strftime('%H%M%S')}{spec.suffix}"
            spec.replace(target)

    def _workspace(self, uid: str) -> Path:
        return self.root / "out" / f"gen_{uid}"

    def _record_artifact(self, uid: str, stage: str, art) -> None:
        if isinstance(art, dict):
            type_ = str(art.get("type") or stage)
            path = art.get("path")
            meta = {k: v for k, v in art.items() if k not in ("type", "path")} or None
        else:
            type_, path, meta = stage, art, None
        # 同一个 (type, path) 只登记一次：job 建立时已登记的 spec 不必在 plan 阶段重登。
        if path is not None:
            existing = {str(a.get("path")) for a in self.store.list_artifacts(uid, type_)}
            if str(path) in existing:
                return
        with suppress(Exception):
            self.store.add_artifact(uid, type_, path, stage=stage, meta=meta)

    def _log(self, message: str) -> None:
        print(message, flush=True)


def _fingerprint(path: Path) -> str | None:
    with suppress(OSError):
        return sha256_of(Path(path).read_bytes())
    return None


orchestrator = PipelineOrchestrator()


def start_production(*, goal: str = "", count: int | None = None, dry: bool | None = None,
                     source: str = "api", console: dict | None = None,
                     stages: list[str] | None = None, specs: list | None = None,
                     force: bool = False, background: bool = True) -> dict:
    """三条入口（WebUI / CLI / Hermes）共用的唯一生产入口。"""
    cfg = RunConfig.from_console(console if console is not None else console_state(),
                                 goal=goal, source=source, dry=dry, stages=stages,
                                 count=count, force=force)
    return orchestrator.start(cfg, background=background, specs=specs)
