"""创意选择器（products / genres / angles / ideas）基线回归（Phase 0）。"""
from __future__ import annotations

import pytest

import lib.angles as angles
import lib.genres as genres
import lib.ideas as ideas
import lib.products as products

pytestmark = pytest.mark.unit


def test_next_genre_is_least_used(tmp_state):
    chosen = genres.next_genre()
    counts = genres.used_count()
    assert counts[chosen["id"]] == min(counts.values())


def test_genre_pool_has_diversity(tmp_state):
    ids = {g["id"] for g in genres.GENRES}
    assert len(ids) >= 10
    assert ids == {f"G{i}" for i in range(1, 11)}


def test_next_angle_skips_used_up(tmp_state):
    a = angles.next_angle()  # 首次为空
    angles.record_angle(a["id"], "job_1")
    assert angles.next_angle()["id"] != a["id"]


def test_next_angle_raises_when_exhausted(tmp_state):
    for a in angles.ANGLES:
        if not a.get("used_up"):
            angles.record_angle(a["id"], "job_x")
    with pytest.raises(RuntimeError):
        angles.next_angle()


def test_next_point_prefers_fewest_uses(tmp_state):
    p1 = products.next_point()
    products.record_point(p1["id"], "job_1")
    p2 = products.next_point()
    assert p2["id"] != p1["id"]


def test_template_fit_restricts_pool(tmp_state):
    fitted = products.TEMPLATE_FIT["T01"]
    for _ in range(len(fitted)):
        assert products.next_point("T01")["id"] in fitted


def test_products_pool_ids_unique(tmp_state):
    ids = [p["id"] for p in products.SALES_POINTS]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 20


def test_record_idea_dedupes_by_template_and_hotspot(tmp_state):
    ideas.record_idea("T01", "换车", "同一个热点", {"1": "a"})
    ideas.record_idea("T01", "换车", "同一个热点", {"1": "b"})
    assert len(ideas.load_ideas()) == 1
