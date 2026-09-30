"""定点修复计划（Phase 8）—— 把 error_code 翻译成"改什么、从哪一步重做"。

与 `errors.REPAIR_MAP` 的分工：
  · `REPAIR_MAP` 管"允许做什么动作"（Phase 4 白名单，表外一律 ABORT，不许猜）；
  · 本模块管"这个动作具体落在哪个 stage、要改什么"（Phase 8 闭环）。

铁律（对应计划 §Phase 8 Repair 映射）：
  · 只重做必要部分 —— 字幕只重建字幕、下载失败只重下、文案违规绝不放行去"重生"；
  · 每条都有可读 instructions，落 DB + 事件流，事后能回答"为什么又跑了一遍、花了钱没"。

`rewind_to` 是 job 级"回退重做"的目标 stage："" = 就在当前 stage 重跑（瞬时错误），
其余值 = 从该 stage 重新往前走（`service._run_stages` 的修复环）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import (
    ASR_MISMATCH,
    COMPLIANCE_BLOCK,
    COMPRESS_PROMPT,
    DOWNLOAD_FAILED,
    HUMAN_ANATOMY_FAIL,
    PRODUCT_DEFORMED,
    PROMPT_BUDGET_EXCEEDED,
    PROMPT_TOO_LONG,
    QA_FAILED,
    REBUILD_SUBTITLE,
    REGENERATE_SHOT,
    REQUIRE_HUMAN,
    RETRY_SAME,
    SUBTITLE_ALIGN_FAIL,
    SWITCH_WORKFLOW,
    VISUAL_QA_FAIL,
    WRONG_SPEAKER,
    repair_action_for,
)

# 动作 → 回退到哪个 stage 重做（"" = 当前 stage 就地重跑）
REPAIR_TARGET: dict[str, str] = {
    RETRY_SAME: "",
    SWITCH_WORKFLOW: "generate",
    COMPRESS_PROMPT: "generate",
    REGENERATE_SHOT: "generate",
    REBUILD_SUBTITLE: "compose",
}

# 计划 §Phase 8 Repair 映射示例 —— 逐条落成可执行说明
PLAYBOOK: dict[str, tuple[str, ...]] = {
    PROMPT_TOO_LONG: (
        "压缩 prompt（去重重复约束、精简修饰）后再提交",
        "不生成 —— 超限的提交必被服务端拒收，白等一次",
    ),
    PROMPT_BUDGET_EXCEEDED: (
        "压缩 prompt（去重重复约束、精简修饰）后再提交",
        "不生成 —— 编译期已超硬上限",
    ),
    WRONG_SPEAKER: (
        "强化该镜 speaker lock（谁说话、其余人闭嘴不张嘴）",
        "必要时减少同镜角色数量后重生",
    ),
    PRODUCT_DEFORMED: (
        "简化动作/构图，减少人与产品的接触点",
        "加强产品单元素材参考（折叠/正侧/45 度）",
        "优先只重生问题镜，不整条重出",
    ),
    HUMAN_ANATOMY_FAIL: (
        "调整 occupancy / 镜头距离 / 动作复杂度后重生",
        "避开删腿、悬空、多手多脚等设定",
    ),
    ASR_MISMATCH: (
        "区分同音识别与真实漏词：同音只重建字幕",
        "真实漏词 → 缩句或调整节奏后重生",
    ),
    SUBTITLE_ALIGN_FAIL: (
        "只重建字幕，不重新生成视频",
        "字幕时间轴必须来自同一 transcript artifact",
    ),
    DOWNLOAD_FAILED: (
        "只重下 provider artifact（不重新提交付费任务）",
    ),
    COMPLIANCE_BLOCK: (
        "改文案/claim，不允许绕过 gate",
        "口径待核验或缺失 → 交人工补证",
    ),
    VISUAL_QA_FAIL: (
        "按失败维度定点修：人数/身份/构图/留存钩子",
        "只重生问题镜，不整条重出",
    ),
    QA_FAILED: (
        "按 QA 报告的失败维度定点修",
    ),
}


@dataclass
class RepairPlan:
    """一次修复的可执行计划（写进 DB / 事件流）。"""

    error_code: str
    action: str
    rewind_to: str = ""
    instructions: list[str] = field(default_factory=list)
    target_shot: int | None = None
    stage: str = ""
    attempt: int = 1
    budget: int = 0
    detail: dict = field(default_factory=dict)

    @property
    def requires_human(self) -> bool:
        return self.action == REQUIRE_HUMAN

    @property
    def in_stage(self) -> bool:
        return not self.rewind_to or self.rewind_to == self.stage

    def to_dict(self) -> dict:
        return {"error_code": self.error_code, "action": self.action,
                "rewind_to": self.rewind_to, "instructions": list(self.instructions),
                "target_shot": self.target_shot, "stage": self.stage,
                "attempt": self.attempt, "budget": self.budget,
                "requires_human": self.requires_human,
                "detail": dict(self.detail)}

    def summary(self) -> str:
        where = self.rewind_to or self.stage or "同阶段"
        shot = f"（镜 {self.target_shot}）" if self.target_shot is not None else ""
        return f"{self.error_code} → {self.action}{shot}：从「{where}」重做"


def repair_target(action: str, stage: str = "") -> str:
    """动作 → 回退目标 stage；未知动作按"就地重跑"处理（保守，不擅自跳阶段）。"""
    return REPAIR_TARGET.get(action, "")


def plan_repair(error_code: str, *, stage: str = "", attempt: int = 1, budget: int = 0,
                findings: list[dict] | None = None, detail: dict | None = None) -> RepairPlan:
    """由 error_code 生成修复计划（动作取白名单表，绝不猜）。"""
    code = str(error_code or "UNKNOWN")
    action = repair_action_for(code)
    shot = None
    for item in (findings or []):
        if isinstance(item, dict) and item.get("shot") is not None:
            shot = int(item["shot"])
            break
    return RepairPlan(error_code=code, action=action, rewind_to=repair_target(action, stage),
                      instructions=list(PLAYBOOK.get(code, ())),
                      target_shot=shot, stage=stage, attempt=attempt, budget=budget,
                      detail=dict(detail or {}))
