"""Phase 11 单测 —— 跨平台标准化（计划任务 1/7）。

重点证明：缺失不参与统计（不是 0）、样本太少的平台不给百分位、
不同平台的同一原始值会被换算成不同百分位（否则跨平台比较就是错的）。
"""
from __future__ import annotations

import pytest

from s7_learn import normalizer
from s7_learn.normalizer import MIN_SCALE_N, Scale

pytestmark = pytest.mark.unit


def _rows(platform: str, values, *, metric="completion", start=1):
    return [{"uid": f"{platform}{i}", "platform": platform, "post_id": None,
             "snapshot_time": "2026-09-29T09:00:00", "metrics": {metric: v}}
            for i, v in enumerate(values, start=start)]


def test_scale_needs_a_minimum_sample_before_it_produces_percentiles():
    scales = normalizer.platform_scales(_rows("douyin", [0.1, 0.2]))
    assert scales["douyin"] == {}, "样本不足不许产出百分位"
    assert MIN_SCALE_N == 3
    assert normalizer.platform_scales(_rows("douyin", [0.1, 0.2, 0.3]))["douyin"]["completion"].n == 3


def test_scale_maps_p10_to_zero_and_p90_to_one_and_clamps():
    scale = Scale(platform="p", metric="m", n=10, p10=10.0, median=20.0, p90=30.0)
    assert scale.pct(10.0) == 0.0
    assert scale.pct(30.0) == 1.0
    assert scale.pct(20.0) == pytest.approx(0.5, abs=1e-9)
    assert scale.pct(999.0) == 1.0 and scale.pct(-999.0) == 0.0
    assert scale.pct(None) is None, "缺失必须保持 None"


def test_flat_scale_returns_midpoint_instead_of_dividing_by_zero():
    scale = Scale(platform="p", metric="m", n=5, p10=4.0, median=4.0, p90=4.0)
    assert scale.pct(4.0) == 0.5


def test_missing_metric_never_becomes_zero_and_is_excluded_from_the_composite():
    rows = [dict(r, metrics={**r["metrics"], "saves": None}) for r in _rows("douyin", [0.4, 0.5, 0.6])]
    normalized, _ = normalizer.normalize(rows)
    row = normalized[0]
    assert row.norm["saves"] is None
    assert row.composite is not None
    weight_of_completion = normalizer.COMPOSITE_WEIGHTS["completion"]
    assert row.composite == pytest.approx(row.norm["completion"])
    assert weight_of_completion > 0


def test_row_with_no_metrics_has_no_composite_at_all():
    normalized, _ = normalizer.normalize([{"uid": "empty", "platform": "douyin",
                                           "snapshot_time": "t", "metrics": {}}])
    assert normalized[0].composite is None, "一条指标都没有 → None，不是 0"
    assert normalizer.composite_of({"completion": None}) == (None, 0.0)


def test_same_raw_value_lands_at_different_percentiles_per_platform():
    rows = _rows("douyin", [0.40, 0.45, 0.50, 0.55, 0.60]) + _rows("xiaohongshu", [0.05, 0.08, 0.10, 0.12, 0.15])
    normalized, scales = normalizer.normalize(rows)
    by_uid = {r.uid: r for r in normalized}
    # douyin 的 0.45 是低分位；小红书的 0.10 是中位 —— 两者原始值不同但含义都靠平台自比
    assert by_uid["douyin2"].norm["completion"] < 0.35
    assert 0.3 < by_uid["xiaohongshu3"].norm["completion"] < 0.7
    assert scales["douyin"]["completion"].median != scales["xiaohongshu"]["completion"].median


def test_composite_renormalizes_over_available_metrics_only():
    norm = {"completion": 1.0, "saves": 0.0}
    value, weight = normalizer.composite_of(norm)
    expected = normalizer.COMPOSITE_WEIGHTS["completion"] / (
        normalizer.COMPOSITE_WEIGHTS["completion"] + normalizer.COMPOSITE_WEIGHTS["saves"])
    assert value == pytest.approx(expected)
    assert weight == pytest.approx(normalizer.COMPOSITE_WEIGHTS["completion"]
                                   + normalizer.COMPOSITE_WEIGHTS["saves"])


def test_normalized_row_keeps_scale_n_and_missing_list():
    rows = _rows("douyin", [0.4, 0.5, 0.6, 0.7])
    normalized, _ = normalizer.normalize(rows)
    row = normalized[0]
    assert row.scale_n == 4
    assert "likes" in row.missing and "completion" not in row.missing
    assert set(row.to_dict()) == {"uid", "platform", "post_id", "snapshot_time", "metrics",
                                 "missing", "norm", "composite", "scale_n"}
