"""Phase 7 单元 —— ACTING 素材切片（必做任务 4）。

把主档案的 7 个常驻块切成可轮换的角色描写，保证"同一 spec 内不重复同一句"，
而不是把一篇 200 字的原文每镜重复塞进去。
"""
from __future__ import annotations

import pytest

from lib.creative import acting

pytestmark = pytest.mark.unit

CLAUSES = ("tics", "walk", "crack", "eyes", "engine", "soften", "voice")


def test_every_slot_alias_points_at_a_real_profile():
    for slot in acting.PROFILE_ALIAS:
        assert acting.profile_for(slot), slot


def test_unknown_slot_has_no_profile():
    assert acting.profile_for("@nobody_at_all") == ""
    assert acting.profile_for("") == ""


def test_profile_for_accepts_a_profile_id_directly():
    assert acting.profile_for("elder") == "elder"


def test_blocks_split_the_profile_into_seven_named_parts():
    blk = acting.blocks(acting.profile_for("@elder_male"))
    assert set(blk) == set(CLAUSES)
    assert all(v.strip() for v in blk.values())


def test_clauses_follow_the_declared_rotation_order():
    cl = acting.clauses(acting.profile_for("@elder_male"))
    assert [c.split(":", 1)[0] for c in cl] == list(acting.CLAUSE_ORDER)


def test_beat_line_prefixes_the_speaker_and_the_beat_tactic():
    line = acting.beat_line("@mid_male", "钩子")
    assert line.startswith(f"{acting.role_label('@mid_male')}: ")
    assert acting.BEAT_TACTICS["钩子"] in line


def test_beat_line_never_repeats_a_clause_within_one_spec():
    used: set[str] = set()
    beats = ["钩子", "冲突/悬念", "演示/转折", "收口卖点", "回味", "钩子"]
    clauses = []
    for beat in beats:
        line = acting.beat_line("@elder_male", beat, used=used)
        clauses.append(line.split(". ", 1)[1].rstrip("."))
    assert len(set(clauses)) == len(clauses)


def test_beat_line_still_returns_a_directive_for_an_unknown_slot():
    line = acting.beat_line("@ghost", "钩子")
    assert line.startswith("THE SPEAKER: ")
    assert line.rstrip().endswith(".")


def test_unknown_beat_falls_back_to_the_generic_tactic():
    line = acting.beat_line("@elder_male", "不存在的节拍")
    assert acting._DEFAULT_TACTIC in line


def test_slot_tics_cover_every_alias():
    for slot in acting.PROFILE_ALIAS:
        assert acting.SLOT_TICS.get(slot), slot
