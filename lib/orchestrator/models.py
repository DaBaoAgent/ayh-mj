"""编排层数据模型（Phase 3）：StageResult / RunConfig / StageContext。

  · `StageResult` 是 stage 与外界唯一的契约：success/artifacts/metrics/error_code/
    message/next_action —— 上层（WebUI / CLI / Hermes / 学习层）只读这个结构；
  · `RunConfig` 是"这次生产"的运行时快照，原样存进 `jobs.config_snapshot`，
    保证 WebUI / CLI / Hermes 三条入口在 DB 里结构完全一致；
  · `StageContext` 给 stage 提供：job / spec / workspace / 子进程执行器（可被 Cancel
    安全终止）/ 日志。
"""
from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..jobstore import JobState, utc_now
from .errors import STAGE_TIMEOUT, Cancelled, StageFailure

# 现行产线阶段顺序（15 秒 one-take）。Phase 5+ 会在此前后插入 research/script/publish。
STAGE_ORDER: tuple[str, ...] = ("plan", "preflight", "generate", "qa", "compose", "package")

STAGE_LABEL = {
    "plan": "创意策划", "preflight": "预检门禁", "generate": "视频生成",
    "qa": "验片", "compose": "后期合成", "package": "归档打包",
}

# 每个 stage 推进哪些 canonical 状态（沿 LINEAR 逐级前进 → 状态机永远合法）
STAGE_STATES: dict[str, tuple[str, ...]] = {
    "plan": (JobState.RESEARCHING, JobState.SCRIPTING),
    "preflight": (JobState.PREFLIGHT,),
    "generate": (JobState.GENERATING,),
    "qa": (JobState.QA,),
    "compose": (JobState.COMPOSING,),
    "package": (JobState.PACKAGING, JobState.READY),
}

# 前端进度条只认这 6 个旧 id（webui/static/app.js），此处做一次单向映射
FRONTEND_STAGES = ("trend", "copy", "storyboard", "generate", "compose", "publish")
FRONTEND_STAGE = {
    "plan": "copy", "preflight": "storyboard", "generate": "generate",
    "qa": "generate", "compose": "compose", "package": "compose",
}
FRONTEND_TO_STAGES: dict[str, tuple[str, ...]] = {
    "trend": ("plan",), "copy": ("plan",), "storyboard": ("preflight",),
    "generate": ("generate", "qa"), "compose": ("compose", "package"), "publish": (),
}

# "正在跑"的状态（进程重启要收敛为 PAUSED；Stop 要终止的就是这些）。
# PLANNING 是合法的静止态（还没开始），READY 之后的成片已经在等发布 —— 都不算在跑。
INTERRUPTIBLE_STATES: tuple[str, ...] = tuple(
    s for s in JobState.LINEAR
    if s not in (JobState.PLANNING, JobState.READY, JobState.DONE))
ACTIVE_STATES = INTERRUPTIBLE_STATES


@dataclass
class StageResult:
    """stage 结构化输出（Phase 3 契约）。"""

    stage: str
    success: bool
    artifacts: list[Any] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    message: str = ""
    next_action: str = "continue"
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, stage: str, *, artifacts: list[Any] | None = None,
           metrics: dict[str, Any] | None = None, message: str = "",
           data: dict[str, Any] | None = None,
           next_action: str = "continue") -> StageResult:
        return cls(stage=stage, success=True, artifacts=list(artifacts or []),
                   metrics=dict(metrics or {}), message=message,
                   data=dict(data or {}), next_action=next_action)

    @classmethod
    def fail(cls, stage: str, error_code: str, message: str = "", *,
             next_action: str = "stop", metrics: dict[str, Any] | None = None,
             artifacts: list[Any] | None = None,
             data: dict[str, Any] | None = None) -> StageResult:
        return cls(stage=stage, success=False, error_code=error_code,
                   message=message or error_code, next_action=next_action,
                   metrics=dict(metrics or {}), artifacts=list(artifacts or []),
                   data=dict(data or {}))

    @property
    def cost(self) -> float:
        try:
            return float(self.metrics.get("cost") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "success": self.success,
            "artifacts": [str(a) if isinstance(a, (str, Path)) else a for a in self.artifacts],
            "metrics": self.metrics, "error_code": self.error_code,
            "message": self.message, "next_action": self.next_action,
            "data": self.data,
        }


@dataclass
class RunConfig:
    """一次生产运行的配置快照（落进 job.config_snapshot，三条入口结构一致）。"""

    goal: str = ""
    source: str = "cli"
    daily_target: int = 1
    gen_concurrency: int = 6
    dry_mode: bool = False
    real_publish: bool = False
    real_engage: bool = False
    publish_platforms: list[str] = field(default_factory=lambda: ["douyin"])
    stages: list[str] = field(default_factory=lambda: list(STAGE_ORDER))
    max_attempts: int = 3
    max_repairs: int = 3
    budget_cap: float | None = None
    force: bool = False
    created_at: str = ""

    def __post_init__(self) -> None:
        self.daily_target = max(1, min(20, int(self.daily_target or 1)))
        self.gen_concurrency = max(1, min(10, int(self.gen_concurrency or 6)))
        self.max_attempts = max(1, min(5, int(self.max_attempts or 3)))
        self.max_repairs = max(0, min(10, int(self.max_repairs if self.max_repairs is not None else 3)))
        chosen = [s for s in STAGE_ORDER if s in set(self.stages or STAGE_ORDER)]
        self.stages = chosen or list(STAGE_ORDER)
        self.publish_platforms = [str(p) for p in (self.publish_platforms or [])]
        if not self.created_at:
            self.created_at = utc_now()

    def to_dict(self) -> dict:
        return {
            "goal": self.goal, "source": self.source,
            "daily_target": self.daily_target, "gen_concurrency": self.gen_concurrency,
            "dry_mode": self.dry_mode, "real_publish": self.real_publish,
            "real_engage": self.real_engage, "publish_platforms": list(self.publish_platforms),
            "stages": list(self.stages), "max_attempts": self.max_attempts,
            "max_repairs": self.max_repairs,
            "budget_cap": self.budget_cap, "force": self.force,
            "created_at": self.created_at,
        }

    @classmethod
    def from_console(cls, console: dict | None, *, goal: str = "", source: str = "webui",
                     dry: bool | None = None, stages: list[str] | None = None,
                     count: int | None = None, force: bool = False,
                     budget_cap: float | None = None) -> RunConfig:
        """由 WebUI 设置（state/console.json）构造快照；`dry`/`count` 可被请求体覆盖。"""
        c = dict(console or {})
        return cls(
            goal=goal, source=source,
            daily_target=int(count if count is not None else c.get("daily_target", 1) or 1),
            gen_concurrency=int(c.get("gen_concurrency", 6) or 6),
            dry_mode=bool(c.get("dry_mode", False)) if dry is None else bool(dry),
            real_publish=bool(c.get("real_publish", False)),
            real_engage=bool(c.get("real_engage", False)),
            publish_platforms=list(c.get("publish_platforms") or ["douyin"]),
            stages=list(stages) if stages else list(STAGE_ORDER),
            force=force, budget_cap=budget_cap,
        )


@dataclass
class StageContext:
    """stage 执行上下文。子进程一律经 `run_subprocess()`，以便 Cancel 安全终止。"""

    uid: str
    stage: str
    spec: Path | None = None
    job: dict = field(default_factory=dict)
    config: RunConfig = field(default_factory=RunConfig)
    workspace: Path = field(default_factory=Path)
    root: Path = field(default_factory=Path)
    queue_dir: Path | None = None     # 队列 spec 目录（Phase 5：Planner 只往这里写 spec）
    state_dir: Path | None = None     # 状态根目录（Planner 的 research/dna/scores 落这里）
    store: Any = None
    provider: Any = None          # 供应商适配器（Phase 4；缺省时 stage 自己按需构造）
    handle: Any = None
    log: Callable[[str], None] | None = None
    spawned: list[subprocess.Popen] = field(default_factory=list)
    # 幂等生成驱动的可调参数（真实运行用默认值；测试注入 0 延时）
    sleep: Callable[[float], None] = time.sleep
    poll_interval: float = 20.0
    max_wait: float = 1800.0
    download_retries: int = 3

    @property
    def dry(self) -> bool:
        return bool(self.config.dry_mode)

    @property
    def force(self) -> bool:
        return bool(self.config.force)

    @property
    def python(self) -> str:
        return sys.executable

    @property
    def cancel_event(self):
        """当前 run 的取消信号（无 handle 时为 None）——幂等生成驱动据此安全停止。"""
        return getattr(self.handle, "cancel", None)

    def cancelled(self) -> bool:
        event = getattr(self.handle, "cancel", None)
        return bool(event is not None and event.is_set())

    def say(self, message: str) -> None:
        if self.log is not None:
            self.log(message)

    def run_subprocess(self, cmd: list[Any], *, timeout: float | None = None,
                       cwd: Path | None = None,
                       env: dict | None = None) -> subprocess.CompletedProcess:
        """跑子进程；Cancel 时按进程树杀掉子进程并抛 `Cancelled`。"""
        argv = [str(c) for c in cmd]
        self.say("  ▷ " + " ".join(argv))
        proc = subprocess.Popen(  # noqa: S603
            argv, cwd=str(cwd or self.root), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace", env=env)
        self.spawned.append(proc)
        if self.handle is not None:
            self.handle.register_proc(proc)
        deadline = (time.time() + timeout) if timeout else None
        out = ""
        while True:
            try:
                out, _ = proc.communicate(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                if self.cancelled():
                    self._kill(proc)
                    raise Cancelled(f"{self.stage} 阶段被取消（子进程已终止）",
                                    data={"cmd": argv}) from None
                if deadline is not None and time.time() > deadline:
                    self._kill(proc)
                    raise StageFailure(
                        f"{self.stage} 超时（>{timeout:.0f}s）",
                        error_code=STAGE_TIMEOUT, data={"cmd": argv}) from None
        if self.cancelled():   # 取消恰好在子进程退出瞬间到达 → 仍然算取消，不进下游
            self._kill(proc)
            raise Cancelled(f"{self.stage} 阶段被取消（子进程已终止）",
                            data={"cmd": argv}) from None
        if self.handle is not None:
            self.handle.clear_proc(proc)
        return subprocess.CompletedProcess(argv, proc.returncode, out, None)

    def _kill(self, proc: subprocess.Popen) -> None:
        if self.handle is not None:
            self.handle.kill_proc()
        else:  # 没有 handle（单元测试直连）时也要收干净
            with suppress(OSError):
                proc.kill()


def tail_lines(text: str, n: int = 12) -> str:
    """取日志末尾 n 行（失败诊断用，避免把整份日志塞进 DB）。"""
    lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:])[-2000:]
