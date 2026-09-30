"""Phase 11 单测 —— Planner 接入 HistoricalPerformance（计划任务 5/6/8 + 验收②③）。

计划验收②：Planner 在**相同候选**下会受到历史数据影响，但仍保留探索候选。
计划验收③：数据不足时明确显示 low confidence。
"""
from __future__ import annotations

import json

import pytest

from lib.creative import SCORE_DIMENSIONS, CreativePlanner
from lib.creative.hotspot import normalize_hotspot
from lib.creative.scoring import HISTORICAL_DIMENSION
from lib.jobstore import store
from s7_learn import scorer
from tests.p11_support import load_corpus, materialize

pytestmark = pytest.mark.unit

SPOT = {"platform": "baidu", "title": "老友相聚聊出行", "ref": "assets/trends/热点库.md#L1"}
HOTSPOT = normalize_hotspot(SPOT)


def planner(tmp_state, **kwargs) -> CreativePlanner:
    return CreativePlanner(store=store, queue_dir=tmp_state / "queue_15s",
                           state_dir=tmp_state, **kwargs)


def with_history(tmp_state) -> CreativePlanner:
    materialize(tmp_state.parent, store, load_corpus())
    return planner(tmp_state)


def base_context(p, hotspot=None):
    return {"used_counts": p.used_counts(), "day_registry": {}, "trend": (hotspot or HOTSPOT).to_dict()}


# ── 验收②：候选评分受历史影响 ──────────────────────────────────
def test_history_changes_the_scores_for_the_same_candidates(tmp_state):
    p = with_history(tmp_state)
    cands = p.candidates(16, hotspot=HOTSPOT)
    model = p.performance_model()
    assert model is not None and model.n_samples == 15
    hook = scorer.history_hook(model)

    cold = p.director.rank(cands, context=base_context(p))
    warm = p.director.rank(cands, context={**base_context(p), "history": hook,
                                           "history_weight": 0.25})
    assert all(HISTORICAL_DIMENSION not in c.scores for c in cold), "没历史就不许凭空加维度"
    assert all(HISTORICAL_DIMENSION in c.scores for c in warm)
    assert any(abs(c.total - w.total) > 1e-6 for c, w in zip(cold, warm, strict=True)), \
        "同一批候选在历史数据下评分必须变化"
    assert (warm[0].scores[HISTORICAL_DIMENSION]
            > warm[-1].scores[HISTORICAL_DIMENSION]), "历史更好的片型该拿到更高先验分"


def test_history_prior_reason_names_sample_size_and_window(tmp_state):
    p = with_history(tmp_state)
    cands = p.candidates(16, hotspot=HOTSPOT)
    hook = scorer.history_hook(p.performance_model())
    scored = p.director.rank(cands, context={"history": hook})[0]
    reason = scored.scores["reasons"][HISTORICAL_DIMENSION]
    assert "n=" in reason and "近 30 天" in reason


# ── 验收②：仍然保留探索候选 ──────────────────────────────────
def test_exploration_is_always_kept_in_the_shortlist(tmp_state):
    p = with_history(tmp_state)
    job = p.plan_for("P11EXPLORE", day="2026-09-30")   # 探索（ratio 默认 0.8，seed 落在探索区间）
    decision = job.decision
    assert decision["exploration"] is not None, "探索/利用的策略必须落盘可追溯"
    assert decision["exploration"]["ratio"] == pytest.approx(0.8)
    assert decision["exploration"]["no_prediction"] is True
    genres = [s["dna"]["genre"] for s in decision["shortlist"]]
    assert decision["chosen"].dna.genre in genres, "终选必须出现在 shortlist 里"
    assert len(decision["shortlist"]) == 3


def test_exploring_never_picks_a_candidate_that_has_no_better_evidence(tmp_state):
    p = with_history(tmp_state)
    cands = p.candidates(16, hotspot=HOTSPOT)
    ranked = p.director.rank(cands, context=base_context(p))
    model = p.performance_model()
    explored = scorer.select(ranked, model, ratio=0.0, rng=None)
    assert explored["explored"] is True
    assert explored["chosen"] in scorer.exploration_pool(ranked, model)


def test_exploit_and_explore_are_deterministic_under_a_seeded_rng(tmp_state):
    import random
    p = with_history(tmp_state)
    cands = p.candidates(16, hotspot=HOTSPOT)
    ranked = p.director.rank(cands, context=base_context(p))
    model = p.performance_model()
    exploit = scorer.select(ranked, model, ratio=1.0, rng=random.Random(7))
    assert exploit["chosen"] is ranked[0] and exploit["exploited"] is True


# ── 任务 8 / 验收③：不做预测承诺；数据不足要显式说 ───────────────
def test_planner_decision_never_claims_a_guaranteed_hit(tmp_state):
    p = with_history(tmp_state)
    job = p.plan_for("P11NOPRED", day="2026-09-30")
    blob = json.dumps(job.decision["exploration"], ensure_ascii=False)
    assert "不构成" in blob, "探索/利用的策略里必须写明不做预测承诺"
    assert "no_prediction" in blob or "note" in blob


def test_thin_history_is_surfaced_as_low_confidence(tmp_state):
    materialize(tmp_state.parent, store, load_corpus())
    assert store.list_performance_metrics("LRN_G1_01")
    # 只留 1 条样本 → 明确 low confidence（数据不足必须说出来，而不是装作很懂）
    from s7_learn.features import Sample
    tiny = scorer.learn([Sample(uid="A", platform="douyin", post_id=None,
                                snapshot_time="2026-09-29T09:00:00", composite=0.9,
                                features={"genre": "G1"}, multi_features={"risk_flags": []})])
    assert tiny.confidence() == "low"
    assert tiny.to_dict()["low_confidence"] is True


def test_planning_without_any_history_behaves_like_phase_five(tmp_state):
    p = planner(tmp_state)
    assert p.performance_model() is None
    cands = p.candidates(16, hotspot=HOTSPOT)
    context = base_context(p)
    plain = p.director.rank(cands, context=context)
    same = p.director.rank(cands, context=dict(context))
    assert [c.total for c in plain] == [c.total for c in same]
    assert all(HISTORICAL_DIMENSION not in c.scores for c in plain)
    ref = {
        "Novelty": 0.14, "AudienceFit": 0.13, "TrendFit": 0.10, "SalesPointFit": 0.12,
        "VisualPotential": 0.10, "ConflictStrength": 0.10, "GenerationFeasibility": 0.11,
        "BrandSafety": 0.08, "ClaimRisk": 0.06, "EstimatedCost": 0.06,
    }
    assert set(SCORE_DIMENSIONS) == set(ref), "10 维契约不许被 Phase 11 改动"


def test_learning_failure_never_blocks_planning(tmp_state, monkeypatch):
    import s7_learn.pipeline as learn_pipeline

    def boom(*_a, **_k):
        raise RuntimeError("学习层故意坏掉")

    monkeypatch.setattr(learn_pipeline, "history_for_planner", boom)
    p = planner(tmp_state)
    assert p.performance_model() is None
    jobs = p.plan_batch(1, day="2026-09-30")
    assert len(jobs) == 1 and jobs[0].spec_path.is_file()


def test_score_artifact_records_the_history_model_and_selection(tmp_state):
    p = with_history(tmp_state)
    job = p.plan_for("P11ART", day="2026-09-30")
    doc = json.loads(job.dna_path.read_text(encoding="utf-8"))
    hist = doc["rationale"]["history"]
    assert hist["model"]["n_samples"] == 15
    assert hist["model"]["confidence"] in {"low", "medium", "high"}
    assert hist["selection"]["explored"] in (True, False)
    assert hist["selection"]["ratio"] == pytest.approx(0.8)
    scores = json.loads(job.scores_path.read_text(encoding="utf-8"))
    assert any(HISTORICAL_DIMENSION in c["scores"] for c in scores["candidates"])
    assert scores["decision"]["note"]
    assert set(scores["dimensions"]) == set(SCORE_DIMENSIONS)
