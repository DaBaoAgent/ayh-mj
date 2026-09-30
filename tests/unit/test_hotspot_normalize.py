"""Phase 5 必做任务 3 / 4 —— 热点归一化与 source_type 分界。"""
from __future__ import annotations

from datetime import datetime

import pytest

from lib.creative.hotspot import (
    NORMALIZED_FIELDS,
    freshness_of,
    normalize_hotspot,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 30, 12, 0, 0)


def live_row(**over) -> dict:
    row = {"platform": "douyin", "title": "老人摔倒之后全家生活都变了", "likes": 120000,
           "comments": 800, "shares": 300, "score": 88.0, "matched": 1,
           "created_at": "2026-09-29 09:00:00", "video_url": "https://v.douyin.com/abc"}
    row.update(over)
    return row


def test_normalized_fields_are_all_present():
    spot = normalize_hotspot(live_row(), now=NOW).to_dict()
    missing = [f for f in NORMALIZED_FIELDS if f not in spot]
    assert not missing, f"归一化后缺字段：{missing}"
    assert spot["source"] == "douyin"
    assert spot["title"].startswith("老人摔倒")
    assert spot["published_at"] == "2026-09-29 09:00:00"
    assert spot["engagement"] == 120000 + 800 + 300
    assert spot["relevance"] == 1.0
    assert spot["evidence_url"].startswith("https://")


def test_live_row_is_marked_live_with_freshness():
    spot = normalize_hotspot(live_row(), now=NOW)
    assert spot.source_type == "live" and not spot.is_evergreen
    assert 0.9 < (spot.freshness or 0) <= 1.0


def test_library_topic_is_evergreen_with_traceable_evidence_url():
    spot = normalize_hotspot({"platform": "baidu", "title": "健康早餐要包含哪些食物",
                              "ref": "assets/trends/热点库.md#L12"}, now=NOW)
    assert spot.source_type == "evergreen" and spot.is_evergreen
    assert spot.freshness is None, "没有发布时间就不许假装新鲜"
    assert spot.evidence_url.startswith("library://"), "常青素材也要有可追溯证据指针"


def test_engagement_without_publish_date_is_not_live():
    """有互动但没发布时间 → 无法证明"实时"，必须标常青（不许冒充实时热点）。"""
    spot = normalize_hotspot(live_row(created_at=""), now=NOW)
    assert spot.source_type == "evergreen"


def test_evergreen_platform_never_live_even_with_engagement():
    spot = normalize_hotspot(live_row(platform="evergreen"), now=NOW)
    assert spot.source_type == "evergreen"


def test_freshness_decay_and_invalid_input():
    assert freshness_of("2026-09-30 11:00:00", now=NOW) > 0.99
    assert freshness_of("2026-01-01 00:00:00", now=NOW) == 0.0
    assert freshness_of("") is None
    assert freshness_of("不是时间") is None


def test_heat_falls_back_to_engagement_without_score():
    spot = normalize_hotspot(live_row(score=None), now=NOW)
    assert spot.heat == 120000 + 800 + 300
