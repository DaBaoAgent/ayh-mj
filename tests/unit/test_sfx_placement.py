"""Phase 9 单元 —— SFX 动态放置：动作/反转/punchline/品牌 beat + 片型政策。

对应计划 §Phase 9 必做 9/10 与验收「≥5 种 genre 的 BGM/SFX 选择策略明显不同」。
"""
from __future__ import annotations

import pytest

from lib.post import sfx

pytestmark = pytest.mark.unit

LINES = ["老王说走就走真快", "结果我没想到这么快", "爱优护真省心", "这回是真兑现了"]
SPANS = [(0.5, 1.8), (2.0, 3.4), (3.6, 5.0), (5.2, 6.6)]
GENRES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")


def test_triggers_cover_action_reversal_brand_punchline():
    hits = sfx.plan_sfx(SPANS, LINES, genre="G3")
    triggers = {h.trigger for h in hits}
    assert {"action", "reversal", "brand"} <= triggers
    assert all(h.file.endswith(".mp3") for h in hits)
    assert all(h.reason for h in hits)


def test_placement_follows_content_not_fixed_sentence_index():
    """同样的触发句放到不同句序 → 音效点跟着走，不再是固定第 4/5/7/8 句。"""
    a = ["老王说走就走真快", "今天天气不错啊", "爱优护真省心", "就这样吧"]
    b = ["今天天气不错啊", "老王说走就走真快", "就这样吧", "爱优护真省心"]
    ha = [h.at for h in sfx.plan_sfx(SPANS, a, genre="G3")]
    hb = [h.at for h in sfx.plan_sfx(SPANS, b, genre="G3")]
    # 「动作」点跟着台词句走；末句永远有品牌 beat（这是剧情要求，不是固定第 8 句模板）
    assert ha[0] == pytest.approx(SPANS[0][0] - 0.05)
    assert hb[0] == pytest.approx(SPANS[1][0] - 0.05)
    assert len(ha) == 3 and len(hb) == 2
    assert ha != hb


def test_emotional_genre_gets_no_ding_whoosh_pop():
    hits = sfx.plan_sfx(SPANS, LINES, genre="G5")
    assert hits == [], "情感片不许强塞 ding/whoosh/pop"
    assert sfx.policy_for("G5")["max"] == 0


def test_magic_ad_density_exceeds_vlog():
    magic = sfx.plan_sfx(SPANS, LINES, genre="G3")
    vlog = sfx.plan_sfx(SPANS, LINES, genre="G7")
    assert len(magic) > len(vlog)
    assert len(vlog) <= 1, "vlog 要自然，最多 1 个"


def test_at_least_five_genres_have_distinct_sfx_policies():
    policies = {g: (sfx.policy_for(g)["density"], sfx.policy_for(g)["max"],
                    tuple(sfx.policy_for(g)["allow"])) for g in GENRES}
    assert len(set(policies.values())) >= 5, policies
    counts = {g: len(sfx.plan_sfx(SPANS, LINES, genre=g)) for g in GENRES}
    assert len(set(counts.values())) >= 4, counts


def test_hits_respect_cap_order_and_are_not_stacked():
    hits = sfx.plan_sfx(SPANS, LINES, genre="G3")
    assert len(hits) <= sfx.policy_for("G3")["max"]
    assert [h.at for h in hits] == sorted(h.at for h in hits)
    for i, h in enumerate(hits):
        assert all(abs(h.at - other.at) >= 0.15 for other in hits[i + 1:])


def test_beat_map_labels_the_hits():
    story = {"beat_map": [{"index": 1, "beat": "钩子"}, {"index": 2, "beat": "冲突/悬念"},
                          {"index": 3, "beat": "收口卖点"}]}
    hits = sfx.plan_sfx(SPANS, LINES, genre="G3", story=story)
    beats = {h.at: h.beat for h in hits}
    assert beats, hits
    assert "钩子" in beats.values()
    assert any(h.beat == "冲突/悬念" for h in hits)


def test_unknown_genre_uses_default_policy():
    assert sfx.policy_for("G99") == sfx.DEFAULT_POLICY
    assert len(sfx.plan_sfx(SPANS, LINES, genre="G99")) <= sfx.DEFAULT_POLICY["max"]


def test_resolve_files_skips_missing_assets(tmp_path):
    hits = sfx.plan_sfx(SPANS, LINES, genre="G3")
    assert sfx.resolve_files(hits, tmp_path) == []
    for name in {"ding.mp3", "whoosh.mp3", "pop.mp3"}:
        (tmp_path / name).write_bytes(b"x")
    got = sfx.resolve_files(hits, tmp_path)
    assert got and all(p.is_file() for _, p, _ in got)
