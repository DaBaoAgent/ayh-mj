"""2026-10-01 真实生产事故回归：空对白、热点乱配卖点、片型/骨架冲突。"""
from __future__ import annotations

import pytest

from lib import products
from lib.creative.dna import CreativeDNA
from lib.creative.hotspot import normalize_hotspot
from lib.creative.planner import CreativePlanner
from lib.creative.structures import compatible_genres, structure_by_id
from lib.creative.writer import StoryWriter, StoryWritingError, cjk_count, validate_lines
from lib.jobstore import store

pytestmark = pytest.mark.unit

SOLDIER = {
    "platform": "baidu",
    "title": "老兵在天安门不肯坐轮椅起身敬礼",
    "ref": "assets/trends/热点库.md#L5",
}


def _planner(tmp_state) -> CreativePlanner:
    return CreativePlanner(store=store, queue_dir=tmp_state / "queue_15s", state_dir=tmp_state)


def test_soldier_topic_does_not_offer_warranty_as_natural_main_point(tmp_state):
    p = _planner(tmp_state)
    cands = p.candidates(16, hotspot=normalize_hotspot(SOLDIER))
    assert cands
    assert all(dna.sales_point != "warranty_life" for dna, _ in cands)
    assert {dna.sales_point for dna, _ in cands} <= set(products.HUMAN_STORY_POINTS)
    assert {s["id"] for _, s in cands} <= {"S_emotional_story", "S_solo_vlog", "S_pov_first"}
    assert all("@elder_male" in dna.cast_pattern for dna, _ in cands)


def test_every_candidate_genre_matches_its_story_structure(tmp_state):
    cands = _planner(tmp_state).candidates(16, hotspot=normalize_hotspot(SOLDIER))
    for dna, structure in cands:
        allowed = compatible_genres(structure["id"])
        assert not allowed or dna.genre in allowed, (dna.genre, structure["id"], allowed)


def test_warranty_needs_after_sales_context():
    bad, _ = products.sales_point_fit(
        "warranty_life", topic=SOLDIER["title"], structure_id="S_emotional_story", genre_id="G5")
    good, _ = products.sales_point_fit(
        "warranty_life", topic="轮椅坏了以后维修和售后质保怎么办",
        structure_id="S_comment_reply", genre_id="G10")
    assert bad < 0.30
    assert good > 0.80


def _duo_dna() -> CreativeDNA:
    return CreativeDNA(
        audience="子女代购决策者", goal="自然故事", hotspot=SOLDIER["title"], genre="G1", angle="B12",
        sales_point="light_13.8", hook_type="冲突质问", narrative_arc="打脸反转",
        shot_pattern="四镜双人对撞", cast_pattern="@elder_male+@mid_male", product_role="解题工具",
        conflict_type="质疑能力", visual_motif="坡道爬升", camera_language="固定机位中景",
        dialogue_mode="双人对白", audio_mode="现场同期声", payoff="自然落点", ending="自然收尾",
        CTA="轻轻收尾", risk_flags=[])


def test_old_duo_contract_rejects_missing_dialogue():
    structure = structure_by_id("S_duo_conflict")
    problems = validate_lines([], dna=_duo_dna(), structure=structure)
    assert problems
    assert any("8 句" in p for p in problems)


def test_story_writer_fails_closed_when_llm_keeps_returning_empty(monkeypatch):
    structure = structure_by_id("S_duo_conflict")
    monkeypatch.setattr("lib.creative.writer.chat_json", lambda *_a, **_k: {
        "title": "空稿", "goal": "自然故事", "payoff": "自然落点", "ending": "自然收尾",
        "cta": "轻轻收尾", "lines": [], "shot_notes": ["a", "b", "c", "d"],
    })
    writer = StoryWriter(attempts=2)
    with pytest.raises(StoryWritingError):
        writer.write(hotspot={"title": SOLDIER["title"]}, dna=_duo_dna(), structure=structure)


def test_planner_output_never_marks_speech_prompt_ready_without_lines(tmp_state, monkeypatch):
    # 固定真实事故选题，写稿由 conftest 的离线 StoryWriter fake 完成。
    monkeypatch.setattr("lib.creative.planner.build_research_brief", lambda **_k: {
        "hotspot": SOLDIER, "related_topics": [], "viral_examples": [], "benchmark_patterns": [],
        "short_drama_rules": "test", "inventory": {"trends": 1, "bridges": 1, "benchmarks": 1,
                                                      "drama_chars": 4, "missing": []},
    })
    job = _planner(tmp_state).plan_for("REGRESSION_SOLDIER", day="2026-10-01")
    import json
    spec = json.loads(job.spec_path.read_text(encoding="utf-8"))
    mode = spec["creative"]["dna"]["dialogue_mode"]
    if mode != "无对白":
        lines = spec["story_spec"]["lines"]
        assert lines
        assert spec["prompt_ready"] is True
        if mode in {"双人对白", "单人口播", "街访问答", "画外音旁白"}:
            total = sum(cjk_count(row["text"]) for row in lines)
            assert 65 <= total <= 72, (mode, total, lines)
