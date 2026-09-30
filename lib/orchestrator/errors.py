"""编排层异常与 error_code（Phase 3；完整 taxonomy 由 Phase 4 扩展）。

约定
  · 每个异常都带稳定的 `error_code`（UPPERCASE），落进 `jobs.error_code` /
    `attempts.error_code`，前端与 RepairEngine 只认这个码，不解析中文；
  · `retryable` 决定 RepairEngine 是否允许"同阶段重试"；
  · 任何 stage 失败后下游立即停止，除非 RepairEngine 明确给出可继续动作。
"""
from __future__ import annotations


class OrchestratorError(Exception):
    """所有编排层异常的基类。"""

    error_code = "ORCHESTRATOR_ERROR"
    retryable = False

    def __init__(self, message: str = "", *, error_code: str | None = None,
                 data: dict | None = None, next_action: str = "stop") -> None:
        super().__init__(message or self.error_code)
        if error_code:
            self.error_code = error_code
        self.message = message or self.error_code
        self.data = dict(data or {})
        self.next_action = next_action

    def to_dict(self) -> dict:
        return {"error_code": self.error_code, "message": self.message,
                "next_action": self.next_action, "retryable": self.retryable,
                "data": self.data}


class UnknownJob(OrchestratorError):
    error_code = "UNKNOWN_JOB"


class JobNotResumable(OrchestratorError):
    error_code = "JOB_NOT_RESUMABLE"


class StageFailure(OrchestratorError):
    """单个 stage 执行失败（可重试性由具体 error_code 决定）。"""

    error_code = "STAGE_FAILED"
    retryable = True


class CapabilityBlocked(OrchestratorError):
    """环境能力缺失（模型/工具/凭据），不是代码问题。"""

    error_code = "CAPABILITY_BLOCKED"


class BudgetExceeded(OrchestratorError):
    error_code = "BLOCKED_BUDGET"


class Cancelled(OrchestratorError):
    error_code = "CANCEL_REQUESTED"


# ── 阶段级 error_code（Phase 4 扩展为完整 taxonomy）────────────
NO_SPEC = "NO_SPEC"
MISSING_INPUT = "MISSING_INPUT"
PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
GENERATION_FAILED = "GENERATION_FAILED"
QA_FAILED = "QA_FAILED"
COMPOSE_FAILED = "COMPOSE_FAILED"
PACKAGE_FAILED = "PACKAGE_FAILED"
STAGE_TIMEOUT = "STAGE_TIMEOUT"
UNEXPECTED_ERROR = "UNEXPECTED_ERROR"

# 可以"同阶段重试"的 error_code 白名单（RepairEngine 用）
RETRYABLE_CODES = frozenset({GENERATION_FAILED, STAGE_TIMEOUT, UNEXPECTED_ERROR})
