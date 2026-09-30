"""每个 stage 的失败策略（Phase 4 必做任务 6）。

`max_attempts / max_cost / repairable` 是"这个阶段能烧多少钱、能重来几次、允许
自动修哪些错"的唯一声明处：
  · `max_attempts` —— 同一 stage 最多跑几次（含首次）；到顶就交给 RepairEngine 定性；
  · `max_cost`     —— 单次执行的成本天花板（¥）；预估/实测超线即 BLOCKED_BUDGET，
                      在真正付费前就要拦住；
  · `repairable`   —— 该阶段允许就地重跑的 error_code 白名单（⊆ RETRYABLE_CODES）；
                      不在名单里的错误码绝不在本阶段循环。
预算保护是"双层"的：这里管单阶段，`RunConfig.budget_cap` 管整条 job。
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import (
    ASR_MISMATCH,
    DOWNLOAD_FAILED,
    GENERATION_FAILED,
    GENERATION_TIMEOUT,
    HUMAN_ANATOMY_FAIL,
    NETWORK_TRANSIENT,
    PRODUCT_DEFORMED,
    PROMPT_TOO_LONG,
    PROVIDER_REJECTED,
    QA_FAILED,
    RATE_LIMIT,
    STAGE_TIMEOUT,
    SUBTITLE_ALIGN_FAIL,
    UNEXPECTED_ERROR,
    VISUAL_QA_FAIL,
    WRONG_SPEAKER,
)

# 15s/768p 一条 ≈ ¥0.90；给 1.2 倍余量防止"估 0.9 实收 1.0"被判超支
_ONE_TAKE_COST_EST = 1.2

UNKNOWN_CODE = "UNKNOWN"

# 免费阶段：不花钱，可反复跑
_FREE = (UNEXPECTED_ERROR,)
# 生成阶段：网络/限流/超时/失败/拒绝/超长都允许就地重跑（配合退避与换链）
_GENERATE_CODES = (
    NETWORK_TRANSIENT, RATE_LIMIT, DOWNLOAD_FAILED, GENERATION_FAILED,
    GENERATION_TIMEOUT, PROVIDER_REJECTED, PROMPT_TOO_LONG, STAGE_TIMEOUT,
    UNEXPECTED_ERROR,
)
# 后期/质检：转写、字幕对齐错了可以只重跑本阶段
_COMPOSE_CODES = (ASR_MISMATCH, SUBTITLE_ALIGN_FAIL, STAGE_TIMEOUT, UNEXPECTED_ERROR,
                  QA_FAILED, DOWNLOAD_FAILED)
# 验片（Phase 8）：画面/人物/产品/文案的 FAIL 都允许进修复环（回退到 generate 重做），
# 字幕类回退到 compose；上限由 RunConfig.max_repairs 管，绝不死循环。
_QA_CODES = (
    VISUAL_QA_FAIL, PRODUCT_DEFORMED, WRONG_SPEAKER, HUMAN_ANATOMY_FAIL, QA_FAILED,
    ASR_MISMATCH, SUBTITLE_ALIGN_FAIL, DOWNLOAD_FAILED, UNEXPECTED_ERROR,
)


@dataclass(frozen=True)
class StagePolicy:
    """单个 stage 的重试/成本/可修策略。"""

    max_attempts: int = 1
    max_cost: float | None = None
    repairable: tuple[str, ...] = ()
    timeout: float | None = None

    def allows_retry(self, error_code: str | None, attempts: int) -> bool:
        """本阶段是否允许再跑一次（只看阶段策略，不是全局 decide）。"""
        code = error_code or UNKNOWN_CODE
        if code not in self.repairable:
            return False
        return attempts < self.max_attempts

    def to_dict(self) -> dict:
        return {"max_attempts": self.max_attempts, "max_cost": self.max_cost,
                "repairable": list(self.repairable), "timeout": self.timeout}


DEFAULT_POLICY = StagePolicy()

STAGE_POLICIES: dict[str, StagePolicy] = {
    "plan": StagePolicy(max_attempts=2, max_cost=0.0, repairable=_FREE, timeout=120.0),
    "preflight": StagePolicy(max_attempts=2, max_cost=0.0, repairable=_FREE, timeout=300.0),
    "generate": StagePolicy(max_attempts=3, max_cost=_ONE_TAKE_COST_EST,
                            repairable=_GENERATE_CODES, timeout=3600.0),
    "qa": StagePolicy(max_attempts=2, max_cost=0.0, repairable=_QA_CODES, timeout=300.0),
    "compose": StagePolicy(max_attempts=2, max_cost=0.0, repairable=_COMPOSE_CODES,
                           timeout=7200.0),
    "package": StagePolicy(max_attempts=1, max_cost=0.0, repairable=(), timeout=120.0),
    # 未来的付费/高风险阶段（Phase 7+ 接入时会用到）
    "prescreen": StagePolicy(max_attempts=2, max_cost=0.1, repairable=_FREE, timeout=900.0),
    "publish": StagePolicy(max_attempts=1, max_cost=0.0, repairable=(), timeout=600.0),
}


def policy_for(stage: str) -> StagePolicy:
    """取阶段策略；未登记的阶段一律最保守（跑 1 次、不许重试）。"""
    return STAGE_POLICIES.get(stage, DEFAULT_POLICY)
