"""Phase 5 必做任务 7 / 8 / 9 —— 10 维评分与 Creative Director 终选规则。"""
from __future__ import annotations

import pytest

from lib.creative import SCORE_DIMENSIONS, CreativeDirector, score_dna
from lib.creative.dna import CLAIM_RISK_FLAG
from lib.creative.scoring import DIMENSION_WEIGHTS, NUMERIC_CLAIM_POINTS
from lib.creative.structures import STORY_STRUCTURES, structure_by_id
from tests.unit.test_creative_dna import good_dna

pytestmark = pytest.mark.unit

PLAN_DIMENSIONS = {
    "Novelty", "AudienceFit", "TrendFit", "SalesPointFit", "VisualPotential",
    "ConflictStrength", "GenerationFeasibility", "BrandSafety", "ClaimRisk", "EstimatedCost",
}
LIVE_TREND = {"source_type": "live", "relevance": 1.0, "freshness": 0.95, "title": "热榜第一"}
EVERGREEN_TREND = {"source_type": "evergreen", "relevance": 0.6, "freshness": None, "title": "常青"}


def test_dimensions_and_weights_match_plan():
    assert set(SCORE_DIMENSIONS) == PLAN_DIMENSIONS
    assert len(SCORE_DIMENSIONS) == 10
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_covers_every_dimension_with_reasons():
    dna = good_dna(risk_flags=[])
    scores = score_dna(dna, structure=structure_by_id("S_duo_conflict"),
                       context={"trend": LIVE_TREND})
    for dim in SCORE_DIMENSIONS:
        assert 0.0 <= scores[dim] <= 1.0
    assert 0.0 <= scores["total"] <= 1.0
    assert set(scores["reasons"]) == set(SCORE_DIMENSIONS), "每一维都要有可解释理由"


# ── Novelty：使用历史 + 同日重复 ───────────────────────────────
def test_novelty_drops_with_history_and_same_day_repeats():
    dna = good_dna()
    structure = structure_by_id("S_duo_conflict")
    fresh = score_dna(dna, structure=structure, context={"trend": EVERGREEN_TREND})
    used = {"genre": {dna.genre: 3}, "angle": {dna.angle: 2}, "point": {dna.sales_point: 2},
            "group": {dna.cast_pattern: 1}}
    stale = score_dna(dna, structure=structure,
                      context={"trend": EVERGREEN_TREND, "used_counts": used})
    assert stale["Novelty"] < fresh["Novelty"]
    assert "angle×2" in stale["reasons"]["Novelty"]

    same_day = score_dna(dna, structure=structure,
                         context={"trend": EVERGREEN_TREND,
                                  "day_registry": {"hooks": [dna.hook_type],
                                                   "structures": [structure["id"]],
                                                   "shot_patterns": [structure["shot_pattern"]],
                                                   "cast": [dna.cast_pattern]}})
    assert same_day["Novelty"] < fresh["Novelty"] - 0.4


# ── TrendFit / ClaimRisk / EstimatedCost 的方向性 ──────────────
def test_live_hotspot_scores_higher_than_evergreen():
    structure = structure_by_id("S_duo_conflict")
    live = score_dna(good_dna(), structure=structure, context={"trend": LIVE_TREND})
    ever = score_dna(good_dna(), structure=structure, context={"trend": EVERGREEN_TREND})
    assert live["TrendFit"] > ever["TrendFit"]
    assert "evergreen" in ever["reasons"]["TrendFit"]


def test_numeric_claim_lowers_claim_risk_score():
    numeric_point = next(iter(sorted(NUMERIC_CLAIM_POINTS)))
    risky = score_dna(good_dna(sales_point=numeric_point), structure=structure_by_id("S_duo_conflict"),
                      context={"trend": EVERGREEN_TREND})
    safe = score_dna(good_dna(sales_point="cushion_comfy"), structure=structure_by_id("S_duo_conflict"),
                     context={"trend": EVERGREEN_TREND})
    assert risky["ClaimRisk"] < safe["ClaimRisk"]
    reason = score_dna(good_dna(sales_point=numeric_point, risk_flags=[CLAIM_RISK_FLAG]),
                       structure=structure_by_id("S_duo_conflict"),
                       context={"trend": EVERGREEN_TREND})["reasons"]["ClaimRisk"]
    assert "Claims Registry" in reason, reason


def test_estimated_cost_score_inverts_structure_cost():
    cheap = score_dna(good_dna(), structure=structure_by_id("S_magic_loop"),
                      context={"trend": EVERGREEN_TREND})
    pricey = score_dna(good_dna(), structure=structure_by_id("S_emotional_story"),
                       context={"trend": EVERGREEN_TREND})
    assert cheap["EstimatedCost"] > pricey["EstimatedCost"]
    assert cheap["GenerationFeasibility"] > pricey["GenerationFeasibility"]


# ── Creative Director ─────────────────────────────────────────
def test_director_ranks_and_shortlists_top3():
    pairs = [(good_dna(hook_type=h), s) for h, s in zip(
        ["冲突质问", "视觉奇观", "痛点共鸣", "悬念设问", "身份代入"],
        [structure_by_id("S_duo_conflict"), structure_by_id("S_magic_loop"),
         structure_by_id("S_solo_vlog"), structure_by_id("S_suspense_reveal"),
         structure_by_id("S_pov_first")], strict=False)]
    director = CreativeDirector()
    ranked = director.rank(pairs, context={"trend": LIVE_TREND})
    assert [r.total for r in ranked] == sorted((r.total for r in ranked), reverse=True)
    short = director.shortlist(ranked)
    assert len(short) == 3 and short == ranked[:3]

    decision = director.decide(ranked)
    assert decision["chosen"] is ranked[0]
    assert len(decision["shortlist"]) == 3
    assert "第一个未使用" in decision["rule"]
    assert decision["note"]


def test_director_does_not_pick_the_first_candidate():
    """终选必须是"打分最高"，绝不是"候选表里第一个未使用的"。"""
    weak = (good_dna(hook_type="冲突质问"), structure_by_id("S_emotional_story"))
    strong = (good_dna(hook_type="视觉奇观", audience="社区邻里围观者", sales_point="fold_1s"),
              structure_by_id("S_magic_loop"))
    ranked = CreativeDirector().rank([weak, strong], context={"trend": LIVE_TREND})
    assert ranked[0].structure["id"] == "S_magic_loop"
    chosen = CreativeDirector().decide(ranked)["chosen"]
    assert chosen.dna is strong[0], "终选不能退回候选表第一个"


def test_director_is_deterministic():
    pairs = [(good_dna(hook_type=h), s) for h, s in zip(
        ["冲突质问", "视觉奇观", "痛点共鸣"], list(STORY_STRUCTURES)[:3], strict=False)]
    first = CreativeDirector().rank(pairs, context={"trend": LIVE_TREND})
    second = CreativeDirector().rank(list(reversed(pairs)), context={"trend": LIVE_TREND})
    assert [r.dna.to_dict() for r in first] == [r.dna.to_dict() for r in second]
