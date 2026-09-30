"""失败恢复决策（Phase 3 骨架 → Phase 8 扩展为完整 RepairEngine）。

Phase 3 只承担两件事，但这两件事必须是"白名单"式的，绝不猜测：
  1. `decide()`：拿一个失败的 `StageResult`，决定能不能继续（重试 / 停止）。
     只放行明确的 retryable error_code，其余一律停止下游 —— 对应必做任务 7；
  2. `recover_interrupted()`：进程重启后，把"卡在运行中状态"的 job 收敛成
     PAUSED（可恢复），而不是让它们永远假装在跑。
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass

from ..jobstore import InvalidTransition, JobState
from .errors import RETRYABLE_CODES
from .models import INTERRUPTIBLE_STATES, StageResult

# Phase 8 会往这里加"可修复"错误 → 具体修复动作的映射
REPAIRABLE_CODES: frozenset[str] = frozenset()


@dataclass
class RepairDecision:
    action: str          # continue | retry | repair | stop
    reason: str
    error_code: str | None = None

    @property
    def can_continue(self) -> bool:
        return self.action in ("continue", "retry", "repair")


class RepairEngine:
    """阶段失败 → 下一步动作。默认保守：不认识的一律停。"""

    def decide(self, result: StageResult, *, attempts: int = 1,
               max_attempts: int = 3, error_code: str | None = None) -> RepairDecision:
        if result.success:
            return RepairDecision("continue", "阶段成功，进入下游")
        code = error_code or result.error_code
        if result.next_action == "cancel":
            return RepairDecision("stop", "调用方要求取消", code)
        if code in REPAIRABLE_CODES:
            return RepairDecision("repair", f"{code} 有确定性修复动作", code)
        if code in RETRYABLE_CODES:
            if attempts < max_attempts:
                return RepairDecision("retry", f"{code} 可重试（第 {attempts + 1}/{max_attempts} 次）", code)
            return RepairDecision("stop", f"{code} 已连续失败 {attempts} 次，停止（防烧钱）", code)
        return RepairDecision("stop", f"{code or 'UNKNOWN'} 无自动修复动作，停止下游", code)


def recover_interrupted(store, *, active_uids=(), reason: str = "进程重启，任务被打断") -> list[str]:
    """把上一次进程遗留的"运行中"任务收敛为 PAUSED（可 resume）。"""
    active = set(active_uids)
    recovered: list[str] = []
    with suppress(Exception):
        jobs = store.list_jobs(limit=500)
        for job in jobs:
            uid = job.get("uid")
            if not uid or uid in active:
                continue
            if job.get("status") not in INTERRUPTIBLE_STATES:
                continue
            try:
                store.transition(uid, JobState.PAUSED, message=reason,
                                 event_type="interrupted", data={"from": job.get("status")})
            except (InvalidTransition, KeyError, ValueError):
                continue
            recovered.append(uid)
    return recovered
