"""统一执行编排层（Phase 3）：WebUI / CLI / Hermes 共用同一个 Orchestrator。

对外只暴露四件事：
  · `orchestrator` / `start_production()` —— 启动生产的唯一入口；
  · `StageResult` / `RunConfig` —— 阶段契约与配置快照；
  · `PipelineOrchestrator` —— 需要独立实例（测试/多库）时用；
  · `RepairEngine` —— 失败恢复决策。
"""
from .errors import (
    BudgetExceeded,
    Cancelled,
    JobNotResumable,
    OrchestratorError,
    StageFailure,
    UnknownJob,
)
from .models import (
    FRONTEND_STAGE,
    STAGE_LABEL,
    STAGE_ORDER,
    STAGE_STATES,
    RunConfig,
    StageContext,
    StageResult,
)
from .recovery import RepairDecision, RepairEngine
from .service import (
    PipelineOrchestrator,
    console_state,
    kill_process_tree,
    orchestrator,
    start_production,
)

__all__ = [
    "BudgetExceeded", "Cancelled", "FRONTEND_STAGE", "JobNotResumable",
    "OrchestratorError", "PipelineOrchestrator", "RepairDecision", "RepairEngine",
    "RunConfig", "STAGE_LABEL", "STAGE_ORDER", "STAGE_STATES", "StageContext",
    "StageFailure", "StageResult", "UnknownJob", "console_state",
    "kill_process_tree", "orchestrator", "start_production",
]
