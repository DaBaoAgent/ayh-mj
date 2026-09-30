"""统一执行编排层（Phase 3）：WebUI / CLI / Hermes 共用同一个 Orchestrator。

对外只暴露四件事：
  · `orchestrator` / `start_production()` —— 启动生产的唯一入口；
  · `StageResult` / `RunConfig` —— 阶段契约与配置快照；
  · `PipelineOrchestrator` —— 需要独立实例（测试/多库）时用；
  · `RepairEngine` —— 失败恢复决策。
"""
from .errors import (
    ALL_CODES,
    REPAIR_ACTIONS,
    BudgetExceeded,
    Cancelled,
    JobNotResumable,
    OrchestratorError,
    StageFailure,
    UnknownJob,
    repair_action_for,
)
from .generation import (
    PROMPT_MAX,
    PROMPT_SAFE,
    GenerationOutcome,
    IdempotentGenerator,
    compress_prompt,
    ensure_prompt_budget,
)
from .idempotency import fingerprint, fingerprint_parts
from .models import (
    FRONTEND_STAGE,
    STAGE_LABEL,
    STAGE_ORDER,
    STAGE_STATES,
    RunConfig,
    StageContext,
    StageResult,
)
from .policies import StagePolicy, policy_for
from .providers import AutoDLProvider, ProviderTask, build_payload
from .recovery import RepairDecision, RepairEngine
from .service import (
    PipelineOrchestrator,
    console_state,
    kill_process_tree,
    orchestrator,
    start_production,
)

__all__ = [
    "ALL_CODES", "AutoDLProvider", "BudgetExceeded", "Cancelled", "FRONTEND_STAGE",
    "GenerationOutcome", "IdempotentGenerator", "JobNotResumable", "OrchestratorError",
    "PROMPT_MAX", "PROMPT_SAFE", "PipelineOrchestrator", "ProviderTask",
    "REPAIR_ACTIONS", "RepairDecision", "RepairEngine", "RunConfig", "STAGE_LABEL",
    "STAGE_ORDER", "STAGE_STATES", "StageContext", "StageFailure", "StagePolicy",
    "StageResult", "UnknownJob", "build_payload", "compress_prompt", "console_state",
    "ensure_prompt_budget", "fingerprint", "fingerprint_parts", "kill_process_tree",
    "orchestrator", "policy_for", "repair_action_for", "start_production",
]
