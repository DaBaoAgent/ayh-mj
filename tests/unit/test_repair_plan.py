"""Phase 8 —— RepairPlan：error_code → 白名单动作 → 回退到哪个 stage 重做。

对应计划 §Phase 8 的 Repair 映射表（压缩 prompt / 强化 speaker lock / 只重建字幕 / 只重下 / …）。
"""
from __future__ import annotations

import pytest

from lib.orchestrator.errors import (
    ABORT,
    ASR_MISMATCH,
    COMPLIANCE_BLOCK,
    COMPRESS_PROMPT,
    DOWNLOAD_FAILED,
    HUMAN_ANATOMY_FAIL,
    PRODUCT_DEFORMED,
    PROMPT_BUDGET_EXCEEDED,
    PROMPT_TOO_LONG,
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
from lib.orchestrator.repairs import PLAYBOOK, plan_repair, repair_target

pytestmark = pytest.mark.unit

# 计划 §Phase 8 明确列出的映射（error_code → 期望动作）
REQUIRED_MAP = {
    PROMPT_TOO_LONG: COMPRESS_PROMPT,
    WRONG_SPEAKER: REGENERATE_SHOT,
    PRODUCT_DEFORMED: REGENERATE_SHOT,
    HUMAN_ANATOMY_FAIL: REGENERATE_SHOT,
    ASR_MISMATCH: REBUILD_SUBTITLE,
    SUBTITLE_ALIGN_FAIL: REBUILD_SUBTITLE,
    DOWNLOAD_FAILED: RETRY_SAME,
    COMPLIANCE_BLOCK: REQUIRE_HUMAN,
}


@pytest.mark.parametrize("code,action", sorted(REQUIRED_MAP.items()))
def test_plan_uses_the_whitelisted_action(code, action):
    assert repair_action_for(code) == action
    assert plan_repair(code, stage="qa").action == action


@pytest.mark.parametrize("code", sorted(REQUIRED_MAP))
def test_playbook_documents_every_mapped_code(code):
    assert PLAYBOOK.get(code), f"{code} 缺可读修复说明"


def test_rewind_targets_point_at_the_right_stage():
    assert plan_repair(WRONG_SPEAKER, stage="qa").rewind_to == "generate"
    assert plan_repair(PRODUCT_DEFORMED, stage="qa").rewind_to == "generate"
    assert plan_repair(HUMAN_ANATOMY_FAIL, stage="qa").rewind_to == "generate"
    assert plan_repair(PROMPT_TOO_LONG, stage="generate").rewind_to == "generate"
    assert plan_repair(PROMPT_BUDGET_EXCEEDED, stage="generate").rewind_to == "generate"
    assert plan_repair(SUBTITLE_ALIGN_FAIL, stage="qa").rewind_to == "compose"
    # 瞬时错误 / 只重下：就在当前 stage 重跑
    assert plan_repair(DOWNLOAD_FAILED, stage="generate").rewind_to == ""
    assert repair_target(RETRY_SAME) == ""
    assert repair_target(SWITCH_WORKFLOW) == "generate"


def test_unknown_code_falls_back_to_abort_not_guessing():
    plan = plan_repair("SOMETHING_UNSEEN", stage="qa")
    assert plan.action == ABORT and plan.rewind_to == ""
    assert plan.instructions == []
    assert plan.requires_human is False


def test_compliance_failure_is_never_routed_to_regeneration():
    plan = plan_repair(COMPLIANCE_BLOCK, stage="qa")
    assert plan.requires_human and plan.rewind_to == ""
    assert "绕过" in "".join(plan.instructions)


def test_plan_picks_target_shot_from_findings():
    plan = plan_repair(PRODUCT_DEFORMED, stage="qa",
                       findings=[{"dimension": "product", "shot": 3}])
    assert plan.target_shot == 3
    assert "镜 3" in plan.summary()


def test_in_stage_flag_reflects_rewind_target():
    assert plan_repair(DOWNLOAD_FAILED, stage="generate").in_stage is True
    assert plan_repair(PRODUCT_DEFORMED, stage="qa").in_stage is False
    assert plan_repair(VISUAL_QA_FAIL, stage="qa").in_stage is False


def test_plan_to_dict_is_audit_friendly():
    payload = plan_repair(VISUAL_QA_FAIL, stage="qa", attempt=2, budget=3).to_dict()
    for key in ("error_code", "action", "rewind_to", "instructions", "requires_human",
                "attempt", "budget", "stage"):
        assert key in payload
    assert payload["attempt"] == 2 and payload["budget"] == 3
