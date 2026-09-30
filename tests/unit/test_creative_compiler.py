"""Phase 7 单元 —— PromptCompiler（必做任务 2/3/4/5/6/13）。

验收口径：
  · 10 种结构骨架都能编译出非空 prompt，不再被"4 镜 × 8 句"限制；
  · 电影语言（CINEDANCE）按片型动态启用，生活流/街访/情感/悬念不套；
  · 逐镜表演节拍（ACTING）不重复同一句角色描写；
  · 台词渲染三种口径（普通 <d> / 画外音闭合口型 / 画面字幕不念）；
  · 预算器：去重 → 压缩 → 超过硬上限抛 PromptBudgetExceeded（付费前、0 提交）。
"""
from __future__ import annotations

import pytest

from lib.creative import compiler as C
from lib.creative.dna import CreativeDNA
from lib.creative.storiespec import build_story_spec
from lib.creative.structures import STORY_STRUCTURES
from tests.p7_support import STRUCTURE_GENRE, spec_for

pytestmark = pytest.mark.unit

_IDS = [s["id"] for s in STORY_STRUCTURES]


def _by_id(structure_id: str) -> dict:
    return next(s for s in STORY_STRUCTURES if s["id"] == structure_id)


def _compile(structure, **kw):
    return C.compile_spec(spec_for(structure, **kw))


# ── 验收①：10 种骨架各编译一次 ────────────────────────────────────
@pytest.mark.parametrize("structure", STORY_STRUCTURES, ids=_IDS)
def test_every_skeleton_compiles_to_a_nonempty_prompt(structure):
    compiled = _compile(structure)
    assert compiled.prompt.strip()
    assert compiled.uid == f"P7_{structure['id']}"
    assert compiled.shot_count == structure["shots"]
    for layer in ("header", "pace_realism", "product", "music", "hard_tail"):
        assert layer in compiled.layers, layer


@pytest.mark.parametrize("structure", STORY_STRUCTURES, ids=_IDS)
def test_cinedance_follows_the_genre(structure):
    compiled = _compile(structure)
    expected = STRUCTURE_GENRE[structure["id"]] in C.CINEDANCE_GENRES
    assert compiled.cinedance is expected
    assert ("CINEDANCE FILM LANGUAGE" in compiled.prompt) is expected


def test_shot_count_is_driven_by_the_skeleton_not_a_fixed_four():
    five = [s for s in STORY_STRUCTURES if s["shots"] == 5]
    assert five, "骨架库里应当有 5 镜结构"
    assert _compile(five[0]).shot_count == 5
    three = [s for s in STORY_STRUCTURES if s["shots"] == 3]
    assert three
    assert _compile(three[0]).shot_count == 3


def test_line_count_is_not_capped_at_eight():
    structure = _by_id("S_duo_conflict")
    lines = [{"shot": 1 + (i % 4), "speaker": "@elder_male", "text": f"台词{i}"}
             for i in range(12)]
    compiled = C.compile_spec(spec_for(structure, lines=lines))
    assert compiled.line_count == 12
    assert compiled.prompt.count("<d>[Chinese]") == 12


# ── 验收②：逐镜 ACTING 不重复 ────────────────────────────────────
def test_acting_beats_never_repeat_a_clause_within_a_spec():
    compiled = _compile(_by_id("S_duo_conflict"))
    assert compiled.acting_lines
    assert len(set(compiled.acting_lines)) == len(compiled.acting_lines)
    clauses = [ln.split(". ", 1)[1].rstrip(".") for ln in compiled.acting_lines if ". " in ln]
    assert clauses and len(set(clauses)) == len(clauses)


def test_acting_lines_rotate_through_the_profile_blocks():
    from lib.creative import acting

    structure = _by_id("S_duo_conflict")
    slots = structure["cast_pattern"].split("+")
    pools = {s: {c.lower() for c in acting.blocks(acting.profile_for(s)).values()}
             for s in slots}
    by_label = {acting.role_label(s): s for s in slots}
    for line in _compile(structure).acting_lines:
        label, rest = line.split(": ", 1)
        clause = rest.split(". ", 1)[1].rstrip(".").lower() if ". " in rest else ""
        assert label in by_label, label
        assert clause in pools[by_label[label]], (label, clause)


# ── 验收③：台词三种渲染口径 ──────────────────────────────────────
def test_dialogue_lines_use_the_official_d_tag_syntax():
    line = C.spoken_line("@elder_male", "这个真的能行吗", slot_index=1)
    assert line == "(S2) WANG says: <d>[Chinese] 这个真的能行吗</d>"


def test_voiceover_line_declares_closed_lips():
    line = C.spoken_line("@elder_male", "早上出门", slot_index=0, mode="画外音旁白")
    assert "<d>[Chinese] 早上出门</d>" in line
    assert "lips remain completely closed" in line


def test_caption_line_is_visible_text_and_never_spoken():
    line = C.spoken_line("@mid_female", "画面上出现一个神秘包装", slot_index=0, mode="字幕驱动")
    assert "<d>" not in line
    assert "never spoken" in line
    assert "画面上出现一个神秘包装" in line


def test_dialogue_skeleton_carries_speaker_lock_and_chinese_lines():
    prompt = _compile(_by_id("S_duo_conflict")).prompt
    assert "<d>[Chinese] 这个真的能行吗</d>" in prompt
    assert "SPEAKER RULE" in prompt


def test_silent_skeleton_never_claims_someone_speaks():
    prompt = _compile(_by_id("S_magic_loop")).prompt
    assert "says:" not in prompt
    assert "No spoken words in this shot" in prompt


def test_needs_dialogue_matches_the_speech_modes():
    assert C.needs_dialogue("双人对白") is True
    assert C.needs_dialogue("画外音旁白") is True
    assert C.needs_dialogue("字幕驱动") is False
    assert C.needs_dialogue("无对白") is False


# ── 验收④：时间轴 / 预算 / 可追溯 ─────────────────────────────────
@pytest.mark.parametrize("duration,shots,expected", [
    (15, 4, [(0, 4), (4, 8), (8, 12), (12, 15)]),
    (15, 5, [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15)]),
    (10, 3, [(0, 4), (4, 7), (7, 10)]),
])
def test_time_plan_uses_integer_seconds(duration, shots, expected):
    plan = C.time_plan(duration, shots)
    assert plan == expected
    assert plan[0][0] == 0 and plan[-1][1] == duration


def test_budget_dedups_repeated_long_sentences():
    sentence = "This identical long constraint sentence must survive only once inside the prompt."
    prompt, budget = C.budget_prompt(
        [("a", sentence), ("b", sentence + " A second unique tail sentence.")])
    assert budget.dropped_sentences == 1
    assert prompt.count(sentence) == 1
    assert "A second unique tail sentence." in prompt


def test_budget_compresses_whitespace_before_the_safe_line():
    body = "X" * (C.PROMPT_SAFE - 100) + "\n\n" + "Y" * 150
    assert C.PROMPT_SAFE <= len(body) < C.PROMPT_MAX
    prompt, budget = C.budget_prompt([("big", body)])
    assert budget.compressed is True
    assert budget.chars_after < len(body)
    assert len(prompt) <= C.PROMPT_MAX


def test_budget_raises_before_the_provider_when_over_the_hard_limit():
    body = "X" * (C.PROMPT_MAX + 5)
    with pytest.raises(C.PromptBudgetExceeded) as exc:
        C.budget_prompt([("big", body)])
    assert exc.value.chars == len(body)
    assert exc.value.limit == C.PROMPT_MAX
    assert exc.value.error_code == "PROMPT_TOO_LONG"


def test_compiled_prompt_carries_versions_and_facts_digest():
    compiled = _compile(_by_id("S_duo_conflict"))
    assert compiled.compiler_version == C.COMPILER_VERSION
    assert compiled.spec_version
    assert compiled.facts_digest
    meta = compiled.to_dict()
    for key in ("compiler_version", "spec_version", "cinedance", "shot_count",
                "line_count", "facts_digest", "budget", "chars"):
        assert key in meta
    assert meta["chars"] == len(compiled.prompt)


def test_gate_text_wraps_the_prompt_with_duration_for_the_static_gate():
    gate = C.gate_text("hello world", duration=15, resolution="768p竖")
    assert gate.startswith('<h3:video duration="15" resolution="768p竖">')
    assert gate.rstrip().endswith("</text:Value>")
    assert "hello world" in gate


def test_compiling_a_spec_dict_matches_compiling_the_object():
    """Planner 用对象编译、编排器用落盘字典编译 —— 两条路径必须同一份 prompt。"""
    structure = _by_id("S_duo_conflict")
    doc = spec_for(structure, uid="P7_SAME")
    obj = build_story_spec(
        uid="P7_SAME", structure=structure, dna=CreativeDNA(**doc["creative"]["dna"]),
        hotspot={}, research_refs={}, rationale={}, title=doc["title"],
        lines=doc["story_spec"]["lines"], claim_ids=["anti_flip"])
    obj.ref_images = list(doc["ref_images"])
    assert C.compile_spec(obj.to_spec_json()).prompt == C.compile_spec(obj).prompt
