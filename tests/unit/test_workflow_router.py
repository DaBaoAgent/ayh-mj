"""Phase 7 单元 —— 能力感知工作流路由（必做任务 8/9/10）。

  · 需求（时长/图数/音频/首尾帧/文生）先从 spec 读出来；
  · 链条上每一项都必须满足**全部**需求，不兼容的直接拒绝；
  · fallback 绝不静默偷换能力（丢音频 / 丢参考图 / 丢时长）。
"""
from __future__ import annotations

import pytest

from lib.creative.structures import STORY_STRUCTURES
from lib.creative.workflow import (
    MAX_CHAIN,
    WORKFLOW_SPECS,
    Requirement,
    WorkflowIncompatible,
    canonical,
    choose,
    compatible,
    requirements_from_spec,
    route_for_spec,
    validate_chain,
    within_budget,
)
from tests.p7_support import spec_for

pytestmark = pytest.mark.unit


def _by_id(structure_id: str) -> dict:
    return next(s for s in STORY_STRUCTURES if s["id"] == structure_id)


def test_short_alias_is_canonicalised_to_the_capability_table_name():
    assert canonical("multi_image_15s") in WORKFLOW_SPECS
    assert canonical("multi_image") in WORKFLOW_SPECS
    assert canonical("minimax_h3_lightx2v_v5") == "minimax_h3_lightx2v_v5"
    assert canonical("") == ""
    assert canonical("no_such_workflow") == "no_such_workflow"


def test_requirements_are_read_from_the_spec():
    spec = spec_for(_by_id("S_duo_conflict"), duration=15)
    req = requirements_from_spec(spec)
    assert req.duration == 15
    assert req.n_images == 2
    assert req.audio is False
    assert req.quality == "standard"
    assert req.vertical is True
    assert req.first_last is False
    assert req.text_only is False


def test_audio_requirement_follows_ref_audios():
    spec = spec_for(_by_id("S_duo_conflict"))
    spec["ref_audios"] = ["voice.mp3"]
    assert requirements_from_spec(spec).audio is True


def test_duration_mismatch_is_rejected():
    ok, why = compatible("minimax_h3_lightx2v_v5", Requirement(duration=15, n_images=2))
    assert ok is False
    assert "时长" in why


def test_audio_requirement_rejects_a_silent_workflow():
    ok, why = compatible("minimax_h3_lightx2v_v5_15s",
                         Requirement(duration=15, n_images=2, audio=True))
    assert ok is False
    assert "音频" in why


def test_audio_only_workflow_is_rejected_when_there_is_no_audio_reference():
    ok, why = compatible("minimax_h3_zm_u24",
                         Requirement(duration=15, n_images=2, audio=False))
    assert ok is False
    assert "音频输入为前提" in why


def test_reference_image_overflow_is_rejected():
    ok, why = compatible("minimax_h3_z0902", Requirement(duration=10, n_images=9))
    assert ok is False
    assert "参考图" in why


def test_text_only_workflow_is_rejected_when_images_are_required():
    ok, why = compatible("minimax_h3_z0901", Requirement(duration=10, n_images=2))
    assert ok is False
    assert "参考图" in why


def test_first_last_requirement_only_accepts_first_last_workflows():
    ok, _ = compatible("minimax_h3_lightx2v",
                       Requirement(duration=10, n_images=2, first_last=True))
    assert ok is True
    ok, why = compatible("minimax_h3_z0901",
                         Requirement(duration=10, n_images=0, first_last=True))
    assert ok is False
    assert "首尾帧" in why


def test_unknown_workflow_is_never_used_automatically():
    ok, why = compatible("totally_made_up", Requirement())
    assert ok is False
    assert "不在能力表内" in why


def test_choose_raises_when_nothing_can_satisfy_the_requirement():
    with pytest.raises(WorkflowIncompatible) as exc:
        choose(Requirement(duration=15, n_images=0, text_only=True))
    assert exc.value.error_code == "WORKFLOW_INCOMPATIBLE"
    assert exc.value.violations


@pytest.mark.parametrize("structure", STORY_STRUCTURES, ids=[s["id"] for s in STORY_STRUCTURES])
def test_every_skeleton_routes_to_a_capability_preserving_chain(structure):
    spec = spec_for(structure)
    req = requirements_from_spec(spec)
    plan = route_for_spec(spec, risk="medium")
    assert plan.workflow in WORKFLOW_SPECS
    assert validate_chain(plan.chain, req) == []
    assert len(plan.chain) <= MAX_CHAIN
    assert plan.reasons and plan.cost_estimate > 0


def test_ten_second_specs_get_capability_preserving_fallbacks():
    """10s 需求在能力表里不止一个型号满足 —— 首选失败必须能切到兼容 fallback。"""
    spec = spec_for(_by_id("S_duo_conflict"), duration=10)
    req = requirements_from_spec(spec)
    plan = route_for_spec(spec)
    assert plan.fallbacks
    assert validate_chain(plan.chain, req) == []
    for wf in plan.chain:
        assert compatible(wf, req)[0] is True


def test_chain_never_carries_an_incompatible_member():
    for duration in (10, 15):
        for n_images in (0, 2, 9):
            req = Requirement(duration=duration, n_images=n_images)
            try:
                plan = choose(req)
            except WorkflowIncompatible:
                continue
            assert validate_chain(plan.chain, req) == [], (duration, n_images, plan.chain)


def test_rejected_candidates_are_reported_for_audit():
    spec = spec_for(_by_id("S_duo_conflict"), duration=15)
    plan = route_for_spec(spec)
    assert any("时长" in r["reason"] for r in plan.rejected)


def test_within_budget_compares_the_estimate_to_the_cap():
    spec = spec_for(_by_id("S_duo_conflict"))
    plan = route_for_spec(spec)
    assert within_budget(plan, None) is True
    assert within_budget(plan, plan.cost_estimate) is True
    assert within_budget(plan, plan.cost_estimate - 0.01) is False
