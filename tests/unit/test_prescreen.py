"""Phase 7 单元 —— prescreen 风险评分与 5s 预筛 spec（必做任务 11/12）。

高风险新构图不允许直接烧 15s 的钱：必须先跑一段 5s 预筛并留下 passed 结论。
"""
from __future__ import annotations

import pytest

from lib.creative import compiler as C
from lib.creative.prescreen import (
    MANY_PEOPLE,
    PRESCREEN_EVAL,
    PRESCREEN_SECONDS,
    RISK_HIGH,
    build_prescreen_spec,
    needs_prescreen,
    prescreen_passed,
    record_prescreen,
    risk_of,
)
from lib.creative.prescreen import PRESCREEN_EVAL as _EVAL
from lib.creative.structures import STORY_STRUCTURES
from tests.p7_support import spec_for

pytestmark = pytest.mark.unit


def _by_id(structure_id: str) -> dict:
    return next(s for s in STORY_STRUCTURES if s["id"] == structure_id)


def test_low_risk_spec_needs_no_prescreen():
    spec = {"job_uid": "PS_LOW",
            "creative": {"dna": {"cast_pattern": "@elder_male",
                                 "dialogue_mode": "单人口播",
                                 "visual_motif": "轮圈细节",
                                 "conflict_type": "无冲突氛围向", "CTA": ""}}}
    risk = risk_of(spec)
    assert risk["level"] == "low"
    assert risk["reasons"] == []
    assert needs_prescreen(spec) is False


def test_high_risk_spec_requires_prescreen():
    spec = spec_for(_by_id("S_pov_first"))
    risk = risk_of(spec)
    assert risk["level"] == "high"
    assert risk["score"] >= RISK_HIGH
    assert len(risk["reasons"]) >= 3
    assert needs_prescreen(spec) is True


def test_many_people_in_one_frame_adds_risk():
    spec = {"creative": {"dna": {"cast_pattern": "@a+@b+@c", "dialogue_mode": "无对白",
                                 "visual_motif": "", "conflict_type": "", "CTA": ""}}}
    risk = risk_of(spec)
    assert risk["people"] == MANY_PEOPLE
    assert any("3" in r["label"] for r in risk["reasons"])


def test_known_structure_is_no_longer_flagged_as_unproven():
    spec = spec_for(_by_id("S_duo_conflict"))
    unseen = risk_of(spec, seen_structures=())
    seen = risk_of(spec, seen_structures=("S_duo_conflict",))
    assert seen["score"] < unseen["score"]
    assert not any("没拍过" in r["label"] for r in seen["reasons"])


def test_build_prescreen_spec_rewrites_the_chosen_shot_to_five_seconds():
    doc = spec_for(_by_id("S_duo_conflict"))
    doc["prompt"] = C.compile_spec(doc).prompt
    pre = build_prescreen_spec(doc, shot_no=2)
    assert pre["duration"] == PRESCREEN_SECONDS
    assert pre["job_uid"].endswith("_shot2")
    assert pre["prescreen_of"] == doc["job_uid"]
    assert pre["prescreen_shot"] == 2
    assert "[Shot 1, 0 to 5 seconds]" in pre["prompt"]
    assert "[Shot 2," not in pre["prompt"]
    body = pre["prompt"].split("[Shot 1, 0 to 5 seconds]", 1)[1].split("[Shot", 1)[0]
    assert "Hard cut" not in body
    assert "Hard constraints:" not in body, "预筛片段不该把整段硬约束当镜头内容"


def test_build_prescreen_spec_refuses_uncompiled_or_shotless_prompts():
    with pytest.raises(ValueError):
        build_prescreen_spec({"prompt": ""})
    with pytest.raises(ValueError):
        build_prescreen_spec({"prompt": "no shot markers in here"})
    with pytest.raises(ValueError):
        build_prescreen_spec({"prompt": "[Shot 1, 0 to 4 seconds] one shot only"}, shot_no=3)


def test_record_prescreen_and_prescreen_passed(tmp_state):
    from lib.jobstore import store

    uid = "PS_STORE1"
    store.create_job(goal="预筛", uid=uid)
    assert prescreen_passed(store, uid) is False, "没有结论 = 没通过"
    record_prescreen(store, uid, passed=False, detail={"reason": "构图崩"})
    assert prescreen_passed(store, uid) is False
    record_prescreen(store, uid, passed=True, detail={"shot": 1})
    assert prescreen_passed(store, uid) is True
    kinds = [r["kind"] for r in store.list_evaluations(uid, PRESCREEN_EVAL)]
    assert kinds == [_EVAL, _EVAL]
