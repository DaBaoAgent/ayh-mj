"""Phase 10 单测 —— 发布 Gate：完整性 / AI 声明硬字段 / Claims 合规。

对应计划 §Phase 10 验收："发布标题/描述中出现未登记 claim 时被 Compliance Gate 拦截"
与任务 6/7（AI 声明不可绕过、抖音声明确认不了就不许直发）。
"""
from __future__ import annotations

import pytest

from lib.creative.structures import STORY_STRUCTURES
from lib.orchestrator.errors import (
    AI_DISCLOSURE_UNCONFIRMED,
    CLAIM_FORBIDDEN,
    CLAIM_UNMAPPED,
    PACKAGING_INCOMPLETE,
    REQUIRE_HUMAN_PUBLISH,
)
from lib.packaging import build_brief, publish_gate
from tests.p7_support import spec_for

pytestmark = pytest.mark.unit

_BY_ID = {s["id"]: s for s in STORY_STRUCTURES}


def _brief(*, platforms=("douyin",), confirmable=None, **kw) -> dict:
    doc = spec_for(_BY_ID["S_duo_conflict"], uid="P10GATE")
    return build_brief(doc, uid="P10GATE", platforms=list(platforms),
                       disclosure_confirmable=confirmable or {}, **kw)


def test_complete_brief_passes():
    out = publish_gate(_brief())
    assert out.ok, out.message
    assert out.data["claims_gate"] == "pass"
    assert out.data["disclosure"]["douyin"]["verdict"] == "draft_ok"


def test_missing_brief_is_incomplete():
    out = publish_gate(None)
    assert not out.ok and out.code == PACKAGING_INCOMPLETE


@pytest.mark.parametrize("mutate, needle", [
    (lambda b: b.pop("title"), "title"),
    (lambda b: b.pop("description"), "description"),
    (lambda b: b.update(hashtags=[]), "hashtags"),
    (lambda b: b.update(ai_generated=None), "ai_generated"),
    (lambda b: b.pop("claim_ids"), "claim_ids"),
    (lambda b: b.update(title_candidates=b["title_candidates"][:2]), "标题候选"),
    (lambda b: b.update(cover={"text": "", "first_frame": ""}), "cover"),
    (lambda b: b.pop("title_reason"), "选择理由"),
    (lambda b: b.update(targets=[]), "targets"),
])
def test_incomplete_brief_is_rejected(mutate, needle):
    brief = _brief()
    mutate(brief)
    out = publish_gate(brief)
    assert not out.ok and out.code == PACKAGING_INCOMPLETE
    assert needle in out.message


def test_unregistered_number_in_publish_copy_is_blocked():
    brief = _brief()
    brief["title"] = "一次能跑120公里"
    out = publish_gate(brief)
    assert not out.ok and out.code == CLAIM_UNMAPPED
    assert "120" in out.message or "未登记" in out.message


def test_forbidden_rewrite_in_publish_copy_is_blocked():
    """13.8kg 被写成"约20kg" —— 禁用改写，必须拦。"""
    brief = _brief()
    brief["description"] = "约20kg，单手可拎\n点开头像看看同款"
    out = publish_gate(brief)
    assert not out.ok and out.code == CLAIM_FORBIDDEN


def test_unconfirmed_disclosure_blocks_direct_publish():
    """声明没确认却想直发 → 拦下来（这就是"拒绝 direct publish"的证据）。"""
    brief = _brief(confirmable={"douyin": True})
    assert publish_gate(brief).ok
    brief["targets"][0]["mode"] = "direct"
    brief["targets"][0]["ai_disclosure_confirmable"] = False
    out = publish_gate(brief, platforms=["douyin"])
    assert not out.ok and out.code == AI_DISCLOSURE_UNCONFIRMED
    assert "拒绝直发" in out.message


def test_platform_without_draft_channel_requires_human():
    out = publish_gate(_brief(platforms=("instagram",)), platforms=["instagram"])
    assert not out.ok and out.code == REQUIRE_HUMAN_PUBLISH


def test_gate_reports_per_platform_modes():
    out = publish_gate(_brief(platforms=("douyin", "youtube")),
                       platforms=["douyin", "youtube"])
    assert out.ok
    assert out.data["modes"] == {"douyin": "draft", "youtube": "draft"}
