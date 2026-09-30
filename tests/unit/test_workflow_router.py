"""workflow_router 能力矩阵与路由链回归（Phase 0）。"""
from __future__ import annotations

import pytest

from s4_generate import workflow_router as wr

pytestmark = pytest.mark.unit


def test_route_returns_first_choice_then_fallbacks():
    chain = wr.route(n_images=3, has_audio=True, duration=4)
    assert chain[0] == "minimax_h3_zm_u08"
    assert len(chain) >= 2
    assert len(chain) == len(set(chain)), "route 链不应有重复工作流"


def test_route_never_returns_empty():
    for kwargs in [
        dict(n_images=0, text_only=True),
        dict(n_images=1, first_last=True),
        dict(n_images=6, duration=5),
        dict(n_images=3, has_audio=True, duration=15),
    ]:
        assert wr.route(**kwargs)


def test_text_only_route_uses_text2video():
    chain = wr.route(n_images=0, text_only=True, duration=5)
    assert chain[0] == "minimax_h3_lightx2v_no_pic"
    assert wr.WORKFLOW_SPECS[chain[0]]["kind"] == "text2video"


def test_validate_chain_drops_duration_out_of_range():
    chain = ["minimax_h3_b99_003_12s", "minimax_h3_lightx2v_v5"]
    kept = wr.validate_chain(chain, duration=5, has_audio=False)
    assert "minimax_h3_b99_003_12s" not in kept
    assert "minimax_h3_lightx2v_v5" in kept


def test_validate_chain_drops_audio_incapable():
    chain = ["minimax_h3_lightx2v_v5", "minimax_h3_zm_u08"]
    kept = wr.validate_chain(chain, duration=5, has_audio=True)
    assert kept == ["minimax_h3_zm_u08"]


def test_validate_chain_keeps_first_when_all_incompatible():
    chain = ["minimax_h3_b99_003_12s"]
    kept = wr.validate_chain(chain, duration=3, has_audio=False)
    assert kept == ["minimax_h3_b99_003_12s"]


def test_estimate_cost_matches_price_table():
    assert wr.estimate_cost(10, "standard") == pytest.approx(0.6)
    assert wr.estimate_cost(10, "premium") == pytest.approx(1.0)
    assert wr.estimate_cost(10, "draft") == pytest.approx(0.4)


def test_resolution_for_orientation():
    assert wr.resolution_for("standard", vertical=True).endswith("竖")
    assert wr.resolution_for("standard", vertical=False).endswith("横")


def test_every_fallback_target_is_registered():
    for chain in wr.FALLBACK_CHAINS.values():
        for wf in chain:
            assert wf in wr.WORKFLOW_SPECS, f"未注册的 fallback: {wf}"
