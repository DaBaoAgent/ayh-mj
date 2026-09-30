"""Phase 10 单测 —— PackagingAgent：发布物料从 CreativeDNA 生成，不再写死。

对应计划 §Phase 10「PackagingAgent 输出」8 项 + 平台模式裁决。
"""
from __future__ import annotations

import pytest

from lib.creative.structures import STORY_STRUCTURES
from lib.packaging import (
    TITLE_ANGLES,
    build_brief,
    materialize,
    policy_for,
    validate,
)
from tests.p7_support import spec_for

pytestmark = pytest.mark.unit

_BY_ID = {s["id"]: s for s in STORY_STRUCTURES}


def _brief(structure_id: str = "S_duo_conflict", *, platforms=("douyin",),
           confirmable=None, uid: str = "P10PKG", **kw) -> dict:
    doc = spec_for(_BY_ID[structure_id], uid=uid)
    return build_brief(doc, uid=uid, platforms=list(platforms),
                       disclosure_confirmable=confirmable or {},
                       product_keywords=["电动轮椅", "轻便折叠"], **kw)


def test_brief_has_every_required_output_field():
    brief = _brief()
    assert validate(brief) == []
    for key in ("title_candidates", "title", "title_reason", "cover", "description",
                "hashtags", "first_comment_candidates", "claim_ids", "ai_generated",
                "disclosure", "targets"):
        assert key in brief, key


def test_three_candidates_with_distinct_angles_and_a_reason():
    brief = _brief()
    cands = brief["title_candidates"]
    assert len(cands) == 3
    assert {c["angle"] for c in cands} == set(TITLE_ANGLES)
    for c in cands:
        assert c["text"] and c["rationale"] and isinstance(c["score"], float)
    assert brief["title"] in {c["text"] for c in cands}
    assert brief["title_reason"]


def test_brief_is_deterministic_for_the_same_input():
    assert _brief() == _brief()


def test_title_angle_preference_follows_genre():
    """G3（魔性广告）偏爱问句钩子；G5（情感）偏爱卖点直给。"""
    assert _brief("S_magic_loop")["title_angle"] == "hook_question"
    assert _brief("S_emotional_story")["title_angle"] == "benefit"


def test_claim_ids_merged_from_all_three_places():
    doc = spec_for(_BY_ID["S_duo_conflict"], uid="P10CLAIM", claim_ids=["c_top"])
    doc["creative"]["claim_ids"] = ["c_creative", "c_top"]
    doc["story_spec"]["claim_ids"] = ["c_story"]
    brief = build_brief(doc, uid="P10CLAIM", platforms=["douyin"])
    assert brief["claim_ids"] == ["c_top", "c_creative", "c_story"]


def test_brief_survives_an_empty_spec():
    brief = build_brief({}, uid="P10EMPTY", platforms=["douyin"])
    assert validate(brief) == []
    assert brief["title"]


def test_materialize_trims_to_platform_limits():
    brief = _brief(platforms=("xiaohongshu",))
    copy = materialize(brief, "xiaohongshu")
    limit = policy_for("xiaohongshu").max_title_chars
    assert len(copy["title"]) <= limit
    assert len(copy["hashtags"]) <= policy_for("xiaohongshu").max_hashtags
    assert copy["platform"] == "xiaohongshu"


def test_materialize_unknown_platform_raises():
    with pytest.raises(KeyError):
        materialize(_brief(), "myspace")


def test_disclosure_confirmable_platform_may_publish_directly():
    brief = _brief(confirmable={"douyin": True})
    assert brief["disclosure"]["mode"]["douyin"] == "direct"
    assert brief["targets"][0]["ai_disclosure_confirmable"] is True


def test_unconfirmed_disclosure_falls_back_to_draft_then_human():
    """有草稿通道 → draft；没有草稿通道 → require_human。绝不 direct。"""
    brief = _brief(platforms=("douyin", "instagram"))
    modes = brief["disclosure"]["mode"]
    assert modes["douyin"] == "draft"
    assert modes["instagram"] == "require_human"


def test_explicit_mode_overrides_the_verdict():
    brief = _brief(platforms=("douyin",), mode="draft")
    assert brief["disclosure"]["mode"]["douyin"] == "draft"
    assert "显式指定" in brief["targets"][0]["mode_reason"]


def test_targets_carry_window_and_limits():
    brief = _brief(platforms=("douyin",), windows=[{"start": "07:00", "end": "09:00"}])
    target = brief["targets"][0]
    assert target["window"] == {"start": "07:00", "end": "09:00"}
    assert target["max_title_chars"] == policy_for("douyin").max_title_chars
