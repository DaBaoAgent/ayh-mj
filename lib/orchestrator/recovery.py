"""失败恢复决策 —— RepairEngine（Phase 3 骨架 → Phase 4 完整白名单）。

职责边界（重要）：RepairEngine **不做自由 Agent**，只做一件事 ——
拿 `error_code` 去 `errors.REPAIR_MAP` 这个白名单表里查一个动作，然后用
阶段策略（`policies.StagePolicy`）判断"还能不能重来"。表外的 error_code 一律
ABORT，绝不猜、绝不自由发挥（Phase 4 必做任务 8）。

白名单动作（Phase 4 必做任务 9）：
    RETRY_SAME / SWITCH_WORKFLOW / COMPRESS_PROMPT / REGENERATE_SHOT /
    REBUILD_SUBTITLE / WAIT_AND_RESUME / REQUIRE_HUMAN / ABORT

每个 decision 都会被 service 写进 events，并带上"为什么这样修"（reason），
这样"系统自己处理"的每一步都可追溯（必做任务 10）。
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field

from ..jobstore import InvalidTransition, JobState
from .errors import (
    ABORT,
    ACTION_STATE,
    IN_STAGE_ACTIONS,
    REPAIR_MAP,
    UNKNOWN,
    backoff_delay,
    is_transient,
    repair_action_for,
)
from .models import INTERRUPTIBLE_STATES, StageResult
from .policies import policy_for

# 可自动就地修复的 error_code 集合（表驱动的，不是手写清单）
REPAIRABLE_CODES: frozenset[str] = frozenset(
    code for code, action in REPAIR_MAP.items() if action in IN_STAGE_ACTIONS)


@dataclass
class RepairDecision:
    """一次失败 → 下一步动作（带原因，可写入 events）。"""

    action: str                       # 白名单动作之一
    reason: str
    error_code: str | None = None
    delay: float = 0.0                # 重跑前要等的秒数（瞬时错误才有）
    stage: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def in_stage(self) -> bool:
        """是否在原 stage 内自动重跑。"""
        return self.action in IN_STAGE_ACTIONS

    @property
    def can_continue(self) -> bool:
        return self.action == "continue" or self.in_stage

    @property
    def terminal_state(self) -> str | None:
        """非 in-stage 动作对应的 job 终态（None = 不是终态动作）。"""
        return ACTION_STATE.get(self.action)

    def to_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason, "error_code": self.error_code,
                "delay": self.delay, "stage": self.stage, "terminal_state": self.terminal_state}


class RepairEngine:
    """error_code → 白名单动作。默认保守：不认识的一律 ABORT。"""

    def decide(self, result: StageResult, *, attempts: int = 1, max_attempts: int = 3,
               error_code: str | None = None, stage: str | None = None) -> RepairDecision:
        stage = stage or result.stage
        if result.success:
            return RepairDecision("continue", "阶段成功，进入下游", stage=stage)
        code = error_code or result.error_code or UNKNOWN
        if result.next_action == "cancel":
            return RepairDecision(ABORT, "调用方要求取消", code, stage=stage)

        action = repair_action_for(code)
        policy = policy_for(stage) if stage else None
        limit = policy.max_attempts if policy is not None else max_attempts
        # 阶段策略里没登记这个 error_code → 本阶段不允许自动重跑
        if policy is not None and action in IN_STAGE_ACTIONS and code not in policy.repairable:
            return RepairDecision(
                ABORT, f"{code} 不在阶段「{stage}」的可修白名单里，停止（防烧钱）",
                code, stage=stage, meta={"stage_limit": policy.to_dict()})

        if action in IN_STAGE_ACTIONS:
            if attempts < limit:
                delay = backoff_delay(attempts) if is_transient(code) else 0.0
                why = (f"{code} → {action}（第 {attempts + 1}/{limit} 次）"
                       + (f"，退避 {delay:.0f}s" if delay else ""))
                return RepairDecision(action, why, code, delay=delay, stage=stage)
            return RepairDecision(
                ABORT, f"{code} 已连续失败 {attempts} 次（上限 {limit}）→ 停止，不无限烧钱",
                code, stage=stage, meta={"attempts": attempts, "limit": limit})

        # 非 in-stage 动作：WAIT_AND_RESUME（等窗口/配额）/ REQUIRE_HUMAN / ABORT
        reason = {
            "WAIT_AND_RESUME": f"{code}：不是生成失败，等待窗口/配额后恢复（不烧钱）",
            "REQUIRE_HUMAN": f"{code}：需要人工介入（凭据/合规/资产），已暂停自动流程",
            "ABORT": f"{code} 无自动修复动作，停止下游",
        }.get(action, f"{code} → {action}")
        return RepairDecision(action, reason, code, stage=stage)


def recover_interrupted(store, *, active_uids=(), reason: str = "进程重启，任务被打断") -> list[str]:
    """把上一次进程遗留的"运行中"任务收敛为 PAUSED（可 resume）。

    这是 Phase 4 验收场景 1 的前提：崩溃重启后任务不会永远假装在跑，
    已有的 provider task_id 会通过 Resume 走"只查询、不重提交"的路径。
    """
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
