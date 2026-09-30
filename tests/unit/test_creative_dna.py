"""Phase 5 —— CreativeDNA / StorySpec / 结构多样性 基线。"""
from __future__ import annotations

import pytest

from lib.angles import ANGLES
from lib.cast import CAST_SLOTS
from lib.creative import STORY_STRUCTURES, CreativeDNA, build_story_spec, structure_by_id
from lib.creative.dna import (
    AUDIENCES,
    AUDIO_MODES,
    CAMERA_LANGUAGES,
    CLAIM_RISK_FLAG,
    CONFLICT_TYPES,
    DIALOGUE_MODES,
    GOALS,
    HOOK_TYPES,
    NARRATIVE_ARCS,
    PRODUCT_ROLES,
    REQUIRED_FIELDS,
    SHOT_PATTERNS,
    VISUAL_MOTIFS,
)
from lib.creative.storiespec import BEAT_LADDER, build_shots
from lib.genres import GENRES
from lib.products import SALES_POINTS

pytestmark = pytest.mark.unit

# 计划 §Phase 5「CreativeDNA 建议字段」原文 20 项
PLAN_FIELDS = {
    "audience", "goal", "hotspot", "genre", "angle", "sales_point", "hook_type",
    "narrative_arc", "shot_pattern", "cast_pattern", "product_role", "conflict_type",
    "visual_motif", "camera_language", "dialogue_mode", "audio_mode", "payoff",
    "ending", "CTA", "risk_flags",
}
# 计划 §结构多样性要求 原文 10 种
PLAN_STRUCTURES = {
    "双人对撞短剧", "单人Vlog/生活流", "街访/伪纪录", "悬念揭晓", "魔性动作循环",
    "产品实验/对比", "POV 第一人称", "无对白肢体喜剧", "情感故事", "评论区续集/回应型",
}


def good_dna(**over) -> CreativeDNA:
    base = dict(
        audience=AUDIENCES[0], goal=GOALS[0], hotspot="老友相聚聊出行",
        genre=GENRES[0]["id"], angle=ANGLES[0]["id"], sales_point=SALES_POINTS[0]["id"],
        hook_type=HOOK_TYPES[0], narrative_arc=NARRATIVE_ARCS[0], shot_pattern=SHOT_PATTERNS[0],
        cast_pattern="@elder_male+@mid_male", product_role=PRODUCT_ROLES[0],
        conflict_type=CONFLICT_TYPES[0], visual_motif=VISUAL_MOTIFS[0],
        camera_language=CAMERA_LANGUAGES[0], dialogue_mode=DIALOGUE_MODES[0],
        audio_mode=AUDIO_MODES[0], payoff="把松手即停说清楚", ending="停在老人笑着松手",
        CTA="评论区扣 1 帮家里老人看看", risk_flags=[],
    )
    base.update(over)
    return CreativeDNA(**base)


# ── CreativeDNA ────────────────────────────────────────────────
def test_dna_fields_match_plan_exactly():
    assert set(REQUIRED_FIELDS) == PLAN_FIELDS
    assert len(REQUIRED_FIELDS) == 20


def test_dna_validate_passes_for_well_formed_candidate():
    assert good_dna().validate() == []


def test_dna_validate_rejects_missing_and_off_vocab():
    problems = CreativeDNA(hook_type="天马行空不存在的钩子").validate()
    assert any("audience 为空" in p for p in problems)
    assert any("hook_type" in p and "词表" in p for p in problems)


def test_dna_validate_rejects_unknown_pool_ids():
    problems = good_dna(genre="G99", angle="B999", sales_point="ghost").validate()
    assert any("genre" in p for p in problems)
    assert any("angle" in p for p in problems)
    assert any("sales_point" in p for p in problems)


def test_dna_validate_rejects_one_word_payoff():
    assert any("payoff" in p for p in good_dna(payoff="好").validate())


def test_dna_roundtrip_and_signature():
    dna = good_dna(risk_flags=[CLAIM_RISK_FLAG])
    assert CreativeDNA.from_dict(dna.to_dict()) == dna
    assert dna.signature() == (dna.genre, dna.hook_type, dna.shot_pattern)


# ── 结构骨架 ───────────────────────────────────────────────────
def test_structures_cover_all_plan_shapes():
    names = {s["name"] for s in STORY_STRUCTURES}
    assert names >= PLAN_STRUCTURES, f"缺少骨架：{PLAN_STRUCTURES - names}"
    assert len(STORY_STRUCTURES) >= 10
    assert len({s["id"] for s in STORY_STRUCTURES}) == len(STORY_STRUCTURES)


def test_structures_are_distinct_in_shot_pattern_and_arc():
    patterns = [s["shot_pattern"] for s in STORY_STRUCTURES]
    assert len(set(patterns)) == len(patterns), "镜头结构必须两两不同"
    assert len({s["narrative_arc"] for s in STORY_STRUCTURES}) >= 6


def test_structure_vocab_and_cast_slots_are_valid():
    for structure in STORY_STRUCTURES:
        assert structure["shot_pattern"] in SHOT_PATTERNS
        assert structure["narrative_arc"] in NARRATIVE_ARCS
        assert structure["dialogue_mode"] in DIALOGUE_MODES
        assert structure["audio_mode"] in AUDIO_MODES
        assert structure["camera_language"] in CAMERA_LANGUAGES
        assert structure["product_role"] in PRODUCT_ROLES
        assert structure["conflict_type"] in CONFLICT_TYPES
        assert structure["visual_motif"] in VISUAL_MOTIFS
        assert set(structure["hook_types"]) <= set(HOOK_TYPES)
        for slot in structure["cast_pattern"].split("+"):
            assert slot in CAST_SLOTS, f"{structure['id']} 引用了不存在的角色槽位 {slot}"


def test_structure_lookup_and_shots_skeleton():
    structure = structure_by_id("S_duo_conflict")
    shots = build_shots(structure, good_dna())
    assert len(shots) == structure["shots"]
    assert [s["beat"] for s in shots] == list(BEAT_LADDER[: structure["shots"]])
    assert {s["cast_ref"] for s in shots} <= {"@elder_male", "@mid_male"}
    assert shots[1]["visual_motif"] == VISUAL_MOTIFS[0]


# ── StorySpec payload ─────────────────────────────────────────
def test_story_spec_payload_is_queue_ready_and_not_a_prompt():
    dna = good_dna()
    spec = build_story_spec(uid="JOB1", structure=structure_by_id("S_duo_conflict"), dna=dna,
                            hotspot={"title": "老友相聚", "source_type": "evergreen"},
                            research_refs={"hotspot_title": "老友相聚"}, rationale={"note": "x"},
                            title="老友相聚｜冲突质问")
    payload = spec.to_spec_json()
    # make_15s / 编排器需要的键一个不少
    for key in ("job_uid", "title", "prompt", "duration", "resolution", "workflow",
                "ref_images", "ref_audios", "fallback_workflows"):
        assert key in payload, f"spec 缺键 {key}"
    assert payload["plan_only"] is True and payload["prompt_ready"] is False
    assert payload["prompt"] == "", "Phase 5 不许在这里吐 H3 大 prompt"
    assert payload["creative"]["dna"]["genre"] == dna.genre
    assert payload["story_spec"]["shots"], "必须给出结构化镜头节拍"
    assert payload["story_spec"]["structure_id"] == "S_duo_conflict"
