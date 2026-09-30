"""Phase 11 单测 —— 策略评分（计划任务 5–9）。

重点证明：平滑（一条偶然爆/扑不许永久定生死）、置信度分层、
无历史时不假装有、**样本不足一律 low confidence**、80/20 探索与利用可配。
"""
from __future__ import annotations

import random

import pytest

from lib.creative.director import ScoredDNA
from lib.creative.dna import CreativeDNA
from lib.creative.structures import structure_by_id
from s7_learn import scorer
from s7_learn.features import Sample

pytestmark = pytest.mark.unit


def sample(uid: str, genre: str, composite: float | None, *, hook: str = "冲突质问") -> Sample:
    return Sample(uid=uid, platform="douyin", post_id=uid, snapshot_time="2026-09-29T09:00:00",
                  composite=composite, features={"genre": genre, "hook_type": hook},
                  multi_features={"risk_flags": []})


def corpus(genre: str, score: float, n: int, *, hook: str = "冲突质问", start: int = 0) -> list:
    return [sample(f"{genre}-{i}", genre, score, hook=hook) for i in range(start, start + n)]


def dna_for(genre: str, *, hook: str = "冲突质问") -> CreativeDNA:
    from tests.p7_support import dna_for as base_dna_for
    payload = base_dna_for(structure_by_id("S_duo_conflict"))
    payload["genre"] = genre
    payload["hook_type"] = hook
    return CreativeDNA.from_dict(payload)


def ranked(genre: str, total: float, idx: int = 0, *, hook: str = "冲突质问") -> ScoredDNA:
    return ScoredDNA(dna=dna_for(genre, hook=hook), structure={"id": f"S{idx}", "name": f"s{idx}"},
                     scores={"total": total})


# ── 学习与平滑 ─────────────────────────────────────────────────
def test_learn_records_every_conclusion_with_sample_size_and_window():
    samples = corpus("G1", 0.8, 12) + corpus("G5", 0.2, 12)
    model = scorer.learn(samples, window_days=30)
    assert model.n_samples == 24 and model.confidence() == "medium"
    cell = model.cell("genre", "G1")
    assert cell.n == 12 and cell.window_days == 30
    assert cell.mean == pytest.approx(0.8, abs=1e-9)
    assert cell.confidence == "medium"
    assert len(cell.sample_uids) == 12
    assert "近 30 天" in cell.describe() and "n=12" in cell.describe()


def test_samples_without_a_composite_are_excluded_not_treated_as_zero():
    model = scorer.learn(corpus("G1", 0.9, 6) + [sample("X", "G9", None)])
    assert model.n_samples == 6
    assert model.cell("genre", "G9") is None, "没有表现数据的样本不许当 0 计入"


def test_small_samples_are_shrunk_toward_the_global_mean():
    samples = corpus("G1", 1.0, 1) + corpus("G5", 0.0, 20) + corpus("G7", 0.5, 20)
    model = scorer.learn(samples, prior_n=5.0)
    tiny = model.cell("genre", "G1")
    assert tiny.n == 1 and tiny.mean == 1.0
    assert tiny.smoothed < 0.6, "一条偶然爆款必须被拉回均值附近，不能封神"
    assert tiny.smoothed > model.global_mean, "但也不是完全无视这条证据"
    assert tiny.confidence == "low"


def test_confidence_thresholds_are_low_medium_high():
    assert scorer.confidence_for(1, min_medium=8, min_high=30) == "low"
    assert scorer.confidence_for(8, min_medium=8, min_high=30) == "medium"
    assert scorer.confidence_for(29, min_medium=8, min_high=30) == "medium"
    assert scorer.confidence_for(30, min_medium=8, min_high=30) == "high"


def test_global_confidence_reports_data_shortage_explicitly():
    model = scorer.learn(corpus("G1", 0.8, 3))
    assert model.confidence() == "low" and model.low_confidence() is True
    assert model.to_dict()["low_confidence"] is True
    assert model.to_dict()["note"] == scorer.NO_PREDICTION_NOTE


# ── HistoricalPerformance ──────────────────────────────────────
def test_no_history_means_no_pretend_history():
    assert scorer.historical_performance(dna_for("G1"), None) is None
    assert scorer.historical_performance(dna_for("G1"), scorer.learn([])) is None
    assert scorer.history_hook(None) is None


def test_history_distinguishes_better_and_worse_genres():
    model = scorer.learn(corpus("G1", 0.85, 20) + corpus("G5", 0.15, 20))
    good = scorer.historical_performance(dna_for("G1"), model)
    bad = scorer.historical_performance(dna_for("G5"), model)
    assert good["score"] > bad["score"]
    assert good["confidence"] == "medium" and "n=" in good["reason"]


def test_unknown_combination_is_low_confidence_and_not_punished():
    model = scorer.learn(corpus("G1", 0.85, 20) + corpus("G5", 0.15, 20))
    unknown = scorer.historical_performance(dna_for("G99", hook="身份代入"), model)
    assert unknown["insufficient"] is True and unknown["confidence"] == "low"
    assert unknown["score"] == pytest.approx(model.global_mean)
    assert "low confidence" in unknown["reason"]
    assert "探索" in unknown["reason"], "未知组合必须留着探索机会，不能被历史判死"


# ── 探索 / 利用 ────────────────────────────────────────────────
def test_exploration_pool_collects_candidates_without_enough_evidence():
    model = scorer.learn(corpus("G1", 0.85, 20) + corpus("G5", 0.15, 20))
    items = [ranked("G1", 0.9, 1), ranked("G5", 0.8, 2), ranked("G99", 0.7, 3, hook="身份代入")]
    pool = scorer.exploration_pool(items, model)
    assert [i.dna.genre for i in pool] == ["G99"], "只有证据薄弱的才算探索候选"


def test_ratio_is_the_exploitation_probability():
    """ratio = 利用概率：1.0 必然利用、0.0 必然探索（80/20 里的 0.8 就是这个值）。"""
    model = scorer.learn(corpus("G1", 0.85, 20) + corpus("G5", 0.15, 20))
    items = [ranked("G1", 0.9, 1), ranked("G5", 0.8, 2), ranked("G99", 0.7, 3, hook="身份代入")]
    exploit = scorer.select(items, model, ratio=1.0, rng=random.Random(0))
    assert exploit["chosen"] is items[0] and exploit["exploited"] is True
    explore = scorer.select(items, model, ratio=0.0, rng=random.Random(0))
    assert explore["explored"] is True and explore["chosen"].dna.genre == "G99"
    assert explore["exploration_pool"] == 1
    assert explore["no_prediction"] is True
    assert scorer.DEFAULT_EXPLOIT_RATIO == 0.8


def test_select_falls_back_to_exploitation_when_nothing_is_unverified():
    model = scorer.learn(corpus("G1", 0.85, 20) + corpus("G5", 0.15, 20))
    items = [ranked("G1", 0.9, 1), ranked("G5", 0.8, 2)]
    out = scorer.select(items, model, ratio=0.0, rng=random.Random(0))
    assert out["explored"] is False and out["fallback"] is True
    assert "探索池为空" in out["reason"]


def test_select_without_candidates_is_safe():
    out = scorer.select([], None, ratio=0.8)
    assert out["chosen"] is None and out["model_confidence"] == "low"


def test_ratio_is_configurable_and_clamped():
    model = scorer.learn(corpus("G1", 0.85, 20))
    items = [ranked("G1", 0.9, 1), ranked("G99", 0.7, 2, hook="身份代入")]
    assert scorer.select(items, model, ratio=5.0, rng=random.Random(0))["exploited"] is True
    assert scorer.select(items, model, ratio=-1.0, rng=random.Random(0))["explored"] is True


def test_model_is_serialisable_with_thresholds_and_cells():
    model = scorer.learn(corpus("G1", 0.8, 12), window_days=7)
    doc = model.to_dict()
    assert doc["thresholds"] == {"min_medium": 8, "min_high": 30}
    assert doc["window_days"] == 7
    assert doc["cells"]["genre"]["G1"]["n"] == 12
    assert doc["global_mean"] is not None
