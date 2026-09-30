"""PipelineOrchestrator 回归（Phase 3）。

覆盖验收标准：
  · WebUI / CLI / Hermes 三条入口创建的任务在 DB 中结构完全一致；
  · daily_target=2 → 恰好 2 个 job（不多不少）；
  · gen_concurrency 真正限制并行任务数；
  · Cancel 是协作式的：无孤儿子进程，job 明确进 CANCELLED；
  · 进程重启不影响已存在 job 的查询与恢复；
  · 任一 stage 失败即停止下游（除非 RepairEngine 放行）。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator.errors import GENERATION_FAILED, PREFLIGHT_FAILED
from lib.orchestrator.models import STAGE_ORDER

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent.parent


def _stages(**overrides):
    """全绿假 stage 集合（可按需替换单个阶段）。"""
    def make(name):
        def fn(ctx):
            return StageResult.ok(name, metrics={})
        return fn
    stages = {name: make(name) for name in STAGE_ORDER}
    stages.update(overrides)
    return stages


def _orch(tmp_state, stages=None):
    return PipelineOrchestrator(
        store=store, stages=stages or _stages(),
        queue_dir=tmp_state / "queue_15s", root=tmp_state)


def _cfg(**kw) -> RunConfig:
    kw.setdefault("source", "test")
    return RunConfig(**kw)


# ── 1. 三条入口结构一致 ────────────────────────────────────────
def _shape(job: dict) -> dict:
    return {
        "columns": sorted(job),
        "config_keys": sorted(json.loads(job["config_snapshot"])),
        "status": job["status"],
    }


def test_webui_cli_hermes_create_identical_jobs(tmp_state):
    from fastapi.testclient import TestClient

    from lib.orchestrator import orchestrator as shared
    from tools import orchestrate
    from webui import hermes_bridge, server

    # ① CLI（阻塞执行）
    assert orchestrate.main(["start", "--dry", "--count", "1", "--goal", "入口一致性 CLI"]) == 0
    uid_cli = store.list_jobs(limit=1)[0]["uid"]

    # ② WebUI（走同一个 /api/start 端点）
    client = TestClient(server.app)
    resp = client.post("/api/start", json={"dry": True, "count": 1, "goal": "入口一致性 WebUI"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"]
    shared.wait(timeout=30)
    uid_web = resp.json()["jobs"][0]

    # ③ Hermes（同一个 Orchestrator 接口）
    result = hermes_bridge.request_production(goal="入口一致性 Hermes", count=1, dry=True)
    assert result["ok"]
    shared.wait(timeout=30)
    uid_hermes = result["jobs"][0]

    shapes = [_shape(store.get_job(u)) for u in (uid_cli, uid_web, uid_hermes)]
    assert shapes[0] == shapes[1] == shapes[2]
    assert shapes[0]["status"] == JobState.READY

    # 事件序列（成功路径）也必须一致：created + 每阶段 start/end + 状态推进
    kinds = [tuple(e["type"] for e in store.list_events(u)) for u in (uid_cli, uid_web, uid_hermes)]
    assert kinds[0] == kinds[1] == kinds[2]
    assert "stage_start" in kinds[0] and "stage_end" in kinds[0]


# ── 2. daily_target → 恰好 N 个 job（Phase 5：同一天补齐到 daily_target）──
def test_daily_target_creates_exactly_that_many_jobs(tmp_state):
    """Phase 3 契约：一次启动恰好 N 条；Phase 5 语义：同一天按 daily_target 补齐，不超额。"""
    orch = _orch(tmp_state)
    result = orch.start(_cfg(goal="每日目标", daily_target=2), background=False)
    assert result["ok"] and result["count"] == 2
    assert store.counts()["total"] == 2
    assert all(store.get_job(u)["status"] == JobState.READY for u in result["jobs"])

    # 同一天再点一次 Start：今日已补齐 → 不再超额生产（Phase 5 任务 1，省钱且不刷屏）
    result2 = orch.start(_cfg(goal="每日目标", daily_target=2), background=False)
    assert result2["ok"] is True and result2["count"] == 0
    assert store.counts()["total"] == 2

    # 提高今日目标 → 只补差额，绝不重跑已完成的那两条
    result3 = orch.start(_cfg(goal="每日目标", daily_target=3), background=False)
    assert result3["count"] == 1
    assert store.counts()["total"] == 3
    assert not (set(result["jobs"]) & set(result3["jobs"]))


def test_empty_queue_auto_plans_without_manual_spec(tmp_state):
    """Phase 5 验收①：空队列点 Start → 系统自主产出 job + CreativeDNA（不依赖人工塞 spec）。"""
    from lib.orchestrator import stages as stages_mod
    orch = _orch(tmp_state, _stages(plan=stages_mod.stage_plan))
    result = orch.start(_cfg(daily_target=1), background=False)
    assert result["ok"] is True and result["count"] == 1, result
    uid = result["jobs"][0]
    assert store.get_job(uid)["status"] == JobState.READY

    arts = {a["type"]: a["path"] for a in store.list_artifacts(uid)}
    assert {"spec", "research", "creative_dna", "creative_scores"} <= set(arts)
    for kind in ("research", "creative_dna", "creative_scores"):
        assert Path(arts[kind]).is_file(), f"{kind} 未落盘：{arts[kind]}"
    # spec 出片后按 Phase 3 口径归档进 queue/_done，artifact 只是历史指针
    assert Path(arts["spec"]).name in {p.name for p in
                                       (tmp_state / "queue_15s" / "_done").glob("*.json")}
    dna = json.loads(Path(arts["creative_dna"]).read_text(encoding="utf-8"))["dna"]
    assert dna["genre"] and dna["hook_type"] and dna["shot_pattern"] and dna["audience"]
    # 规划过程也要在事件流里可追溯
    assert any(e["type"] == "stage_end" and e["stage"] == "plan" for e in store.list_events(uid))


# ── 3. gen_concurrency 真正限制并行 ───────────────────────────
def test_gen_concurrency_limits_parallel_jobs(tmp_state):
    lock = threading.Lock()
    live = {"active": 0, "peak": 0}

    def slow_generate(ctx):
        with lock:
            live["active"] += 1
            live["peak"] = max(live["peak"], live["active"])
        time.sleep(0.3)
        with lock:
            live["active"] -= 1
        return StageResult.ok("generate", metrics={"cost": 0.0})

    orch = _orch(tmp_state, _stages(generate=slow_generate))
    cfg = _cfg(goal="并发上限", daily_target=6, gen_concurrency=2)
    result = orch.start(cfg, background=True)
    assert result["count"] == 6
    orch.wait(timeout=60)

    assert live["peak"] == 2, f"并行数 {live['peak']} 应被 gen_concurrency=2 限制"
    assert all(store.get_job(u)["status"] == JobState.READY for u in result["jobs"])


# ── 4. 协作式取消：无孤儿子进程 ───────────────────────────────
def test_cancel_is_cooperative_and_leaves_no_orphan(tmp_state):
    captured = []

    def blocking_generate(ctx):
        captured.append(ctx)
        ctx.run_subprocess([sys.executable, "-c", "import time; time.sleep(30)"])
        return StageResult.ok("generate")

    orch = _orch(tmp_state, _stages(generate=blocking_generate))
    result = orch.start(_cfg(goal="取消测试", daily_target=1), background=True)
    uid = result["jobs"][0]

    deadline = time.time() + 20
    while time.time() < deadline and not (captured and captured[0].spawned):
        time.sleep(0.1)
    assert captured, "generate 阶段未进入"
    assert captured[0].spawned, "generate 的子进程未登记（captured/spawned 竞态）"
    proc = captured[0].spawned[0]
    assert proc.poll() is None, "子进程应仍在运行"

    assert orch.cancel(uid)["count"] == 1
    orch.wait(timeout=30)

    assert proc.poll() is not None, "Cancel 后子进程必须已被终止（无孤儿）"
    job = store.get_job(uid)
    assert job["status"] == JobState.CANCELLED
    events = store.list_events(uid)
    assert any(e["type"] == "cancel_requested" for e in events)
    assert any(e["type"] == "cancelled" for e in events)


def test_cancel_without_active_handle_is_immediate(tmp_state):
    orch = _orch(tmp_state)
    uid = store.create_job(goal="待取消", uid="IDLE01")
    store.transition(uid, JobState.RESEARCHING)
    assert orch.cancel(uid)["count"] == 1
    assert store.get_job(uid)["status"] == JobState.CANCELLED


def test_cancel_all_only_touches_running_jobs(tmp_state):
    """Stop 按钮只终止"正在跑"的任务：已就绪的成片、还没开始的任务都不受影响。"""
    orch = _orch(tmp_state)
    ready = orch.start(_cfg(goal="已完成", daily_target=1), background=False)["jobs"][0]
    pending = store.create_job(goal="排队中", uid="PENDING01")
    live = store.create_job(goal="在跑", uid="RUNNING01")
    for name in (JobState.RESEARCHING, JobState.SCRIPTING, JobState.PREFLIGHT,
                 JobState.GENERATING):
        store.transition(live, name)

    out = orch.cancel(all=True)
    assert out["cancelled"] == ["RUNNING01"]
    assert store.get_job(ready)["status"] == JobState.READY
    assert store.get_job(pending)["status"] == JobState.PLANNING
    assert store.get_job(live)["status"] == JobState.CANCELLED


# ── 5. 重启不影响已存在 job 的查询与恢复 ──────────────────────
def test_restart_recovers_interrupted_jobs(tmp_state):
    uid = store.create_job(goal="重启恢复", uid="LEGACY01",
                           config_snapshot=_cfg(goal="重启恢复").to_dict())
    for name in (JobState.RESEARCHING, JobState.SCRIPTING, JobState.PREFLIGHT,
                 JobState.GENERATING):
        store.transition(uid, name)

    # 新实例 = 面板重启后（内存态全丢，只剩 JobStore）
    reborn = _orch(tmp_state)
    recovered = reborn.recover_interrupted()
    assert recovered == ["LEGACY01"]
    assert store.get_job(uid)["status"] == JobState.PAUSED
    assert any(e["type"] == "interrupted" for e in store.list_events(uid))

    # 查询不受重启影响
    listed = {j["uid"] for j in store.list_jobs(limit=10)}
    assert "LEGACY01" in listed
    assert reborn.status()["jobs_by_status"].get(JobState.PAUSED) == 1

    # 且可恢复：从被打断的 generate 阶段接着跑完
    resumed = reborn.resume(uid, background=False)
    assert resumed["ok"] and resumed["from_stage"] == "generate"
    assert store.get_job(uid)["status"] == JobState.READY


def test_resume_rejects_terminal_job(tmp_state):
    orch = _orch(tmp_state)
    uid = store.create_job(goal="已完成", uid="DONE01")
    for name in JobState.LINEAR[1:]:
        store.transition(uid, name)
    out = orch.resume(uid)
    assert out["ok"] is False and out["error_code"] == "JOB_NOT_RESUMABLE"


# ── 6. stage 失败即停止下游 ────────────────────────────────────
def test_stage_failure_stops_downstream(tmp_state):
    ran: list[str] = []

    def tracking(name):
        def fn(ctx):
            ran.append(name)
            return StageResult.ok(name)
        return fn

    def failing_preflight(ctx):
        ran.append("preflight")
        return StageResult.fail("preflight", PREFLIGHT_FAILED, "台词字数超限")

    stages = _stages(**{name: tracking(name) for name in STAGE_ORDER})
    stages["preflight"] = failing_preflight
    orch = _orch(tmp_state, stages)
    result = orch.start(_cfg(goal="门禁失败", daily_target=1), background=False)

    uid = result["jobs"][0]
    job = store.get_job(uid)
    assert job["status"] == JobState.FAILED
    assert job["error_code"] == PREFLIGHT_FAILED
    assert ran == ["plan", "preflight"], f"下游必须停止，实际跑了 {ran}"
    assert [a["stage"] for a in store.list_attempts(uid)] == ["plan", "preflight"]
    assert any(e["type"] == "stage_failed" for e in store.list_events(uid))


def test_retryable_stage_retries_then_stops(tmp_state):
    calls = {"n": 0}

    def flaky_generate(ctx):
        calls["n"] += 1
        return StageResult.fail("generate", GENERATION_FAILED, f"第 {calls['n']} 次失败")

    orch = _orch(tmp_state, _stages(generate=flaky_generate))
    cfg = _cfg(goal="重试上限", daily_target=1, max_attempts=3)
    uid = orch.start(cfg, background=False)["jobs"][0]

    assert calls["n"] == 3, "可重试错误应重试到 max_attempts 才停"
    assert store.get_job(uid)["status"] == JobState.FAILED
    attempts = [a for a in store.list_attempts(uid) if a["stage"] == "generate"]
    assert [a["attempt_no"] for a in attempts] == [1, 2, 3]


def test_retry_after_failure_resumes_from_failed_stage(tmp_state):
    state = {"fail": True}

    def gate(ctx):
        if state["fail"]:
            return StageResult.fail("preflight", PREFLIGHT_FAILED, "第一次不过")
        return StageResult.ok("preflight")

    orch = _orch(tmp_state, _stages(preflight=gate))
    result = orch.start(_cfg(goal="重试", daily_target=1), background=False)
    uid = result["jobs"][0]
    assert store.get_job(uid)["status"] == JobState.FAILED

    state["fail"] = False
    out = orch.retry(uid, background=False)
    assert out["ok"] and out["from_stage"] == "preflight"
    job = store.get_job(uid)
    assert job["status"] == JobState.READY and not job["error_code"]


def test_retry_rejects_non_failed_job(tmp_state):
    orch = _orch(tmp_state)
    result = orch.start(_cfg(goal="无需重试", daily_target=1), background=False)
    out = orch.retry(result["jobs"][0])
    assert out["ok"] is False and out["error_code"] == "JOB_NOT_RESUMABLE"


# ── 7. 队列 spec 走同一条链路（幂等 + 出片后归档）──────────────
def test_queue_spec_is_registered_and_archived(tmp_state):
    queue = tmp_state / "queue_15s"
    queue.mkdir(parents=True, exist_ok=True)
    spec = queue / "QUEUE01.json"
    spec.write_text(json.dumps({"job_uid": "QUEUE01", "goal": "队列派发"}),
                    encoding="utf-8")

    orch = _orch(tmp_state)
    result = orch.start(_cfg(daily_target=1), background=False)
    assert result["jobs"] == ["QUEUE01"]
    assert store.get_job("QUEUE01")["status"] == JobState.READY
    assert [a["type"] for a in store.list_artifacts("QUEUE01")] == ["spec"]
    assert not spec.exists() and (queue / "_done" / "QUEUE01.json").exists()

    # 同一个 spec 再丢回队列：已出片的任务不会被重复生产（幂等，不重复烧钱）
    spec.write_text(json.dumps({"job_uid": "QUEUE01", "goal": "队列派发"}), encoding="utf-8")
    again = orch.start(_cfg(daily_target=1), background=False)
    assert again["ok"] is True and again["jobs"] == [] and again["skipped"] == ["QUEUE01"]
    assert store.counts()["total"] == 1


# ── 8. 预算保护 ────────────────────────────────────────────────
def test_budget_cap_blocks_before_paid_stage(tmp_state):
    orch = _orch(tmp_state)
    uid = store.create_job(goal="超预算", uid="BUDGET01", budget_cap=1.0)
    store.add_cost(uid, 1.5)
    cfg = _cfg(goal="超预算", budget_cap=1.0)
    orch._execute(uid, cfg)
    job = store.get_job(uid)
    assert job["status"] == JobState.BLOCKED
    assert job["error_code"] == "BLOCKED_BUDGET"


# ── 9. 前端契约：status() 字段名稳定 ───────────────────────────
def test_status_payload_keeps_frontend_contract(tmp_state):
    orch = _orch(tmp_state)
    status = orch.status()
    for key in ("running", "current_stage", "progress", "message"):
        assert key in status
    assert status["running"] is False
    orch.start(_cfg(goal="契约", daily_target=1), background=False)
    after = orch.status()
    assert after["running"] is False and after["progress"] == 100.0
    assert after["message"] == "完成"


def test_cli_adapter_run_all_forwards(tmp_state, monkeypatch):
    """老的 tools/run_all.py 必须仍然可用（纯 adapter，不再自己编排）。"""
    from tools import run_all
    assert run_all.main(["--dry", "--count", "1", "--only", "generate"]) == 0
    assert store.counts()["total"] == 1
    assert store.list_jobs(limit=1)[0]["status"] == JobState.READY
