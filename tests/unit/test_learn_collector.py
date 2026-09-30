"""Phase 11 单测 —— 只读采集 / 导入表现（计划任务 1/2 +「指标模型」铁律）。

重点证明：
  · 缺失字段一律 NULL，**绝不编造 0**；
  · 重复导入幂等（同一 uid/platform/post_id/snapshot_time 只落一条）；
  · 没有官方只读通道时**拒绝**采集，而不是偷偷用浏览器绕。
"""
from __future__ import annotations

import json

import pytest

from lib.jobstore import store
from s7_learn import collector
from tests.p11_support import FLAT, flat_snapshots, load_corpus

pytestmark = pytest.mark.unit

PLAN_METRICS = {
    "impressions", "views", "skip_2s", "retention_5s", "avg_watch_time", "avg_watch_pct",
    "completion", "rewatches", "likes", "comments", "shares", "saves", "follows",
    "profile_visits", "dms", "conversion_proxy",
}


def test_metric_fields_match_plan():
    assert set(collector.METRIC_FIELDS) == PLAN_METRICS
    assert len(collector.METRIC_FIELDS) == 16


def test_missing_metric_stays_null_and_is_never_coerced_to_zero():
    cleaned = collector.clean_metrics({"likes": 12, "views": None, "comments": ""})
    assert cleaned == {"likes": 12}
    assert "views" not in cleaned and "comments" not in cleaned


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="未知指标"):
        collector.clean_metrics({"follower_count": 1})


def test_snapshot_requires_identity_and_timestamp():
    with pytest.raises(ValueError, match="snapshot_time"):
        collector.normalize_snapshot({"uid": "A", "platform": "douyin", "metrics": {}})
    with pytest.raises(ValueError, match="uid"):
        collector.normalize_snapshot({"platform": "douyin", "snapshot_time": "t", "metrics": {}})


def test_import_is_idempotent(tmp_state):
    snapshots = [{"uid": "LRN_IMP", "platform": "douyin", "post_id": "p1",
                  "snapshot_time": "2026-09-29T09:00:00", "metrics": {"likes": 5}}]
    store.create_job(goal="导入测试", uid="LRN_IMP")
    first = collector.import_snapshots(store, snapshots)
    assert first == {"total": 1, "imported": 1, "skipped": 0, "errors": []}
    second = collector.import_snapshots(store, snapshots)
    assert second["imported"] == 0 and second["skipped"] == 1
    assert len(store.list_performance_metrics("LRN_IMP")) == 1


def test_import_reports_bad_rows_instead_of_swallowing_them(tmp_state):
    store.create_job(goal="导入测试", uid="LRN_IMP2")
    result = collector.import_snapshots(store, [
        {"uid": "LRN_IMP2", "platform": "douyin", "snapshot_time": "2026-09-29T10:00:00",
         "metrics": {"likes": 1}},
        {"uid": "LRN_IMP2", "platform": "douyin", "metrics": {"likes": 2}},   # 缺时间戳
    ])
    assert result["imported"] == 1 and len(result["errors"]) == 1


def test_missing_metrics_land_as_null_not_zero(tmp_state):
    from tests.p11_support import materialize
    materialize(tmp_state.parent, store)
    rows = store.list_performance_metrics("LRN_XHS_01")
    assert rows and rows[0]["impressions"] is None and rows[0]["retention_5s"] is None
    assert rows[0]["likes"] is not None
    collected = collector.collect_from_store(store, uid="LRN_XHS_01")[0]
    assert "impressions" in collected["missing"]
    assert "impressions" not in collected["metrics"]


def test_collect_from_store_is_read_only_and_keeps_all_platforms(tmp_state):
    from tests.p11_support import materialize
    materialize(tmp_state.parent, store)
    rows = collector.collect_from_store(store)
    assert {r["platform"] for r in rows} == {"douyin", "xiaohongshu"}
    assert len(rows) == 16


def test_load_fixture_supports_all_shapes(tmp_path):
    flat = collector.load_fixture(FLAT)
    assert len(flat) == 16 and "uid" in flat[0]
    assert len(load_corpus()["jobs"]) == 16
    payload = {"uid": "A", "platform": "douyin", "snapshot_time": "t", "metrics": {}}
    single = tmp_path / "one.json"
    single.write_text(json.dumps(payload), encoding="utf-8")
    assert collector.load_fixture(single) == [payload]
    arr = tmp_path / "arr.json"
    arr.write_text(json.dumps([payload]), encoding="utf-8")
    assert collector.load_fixture(arr) == [payload]
    lines = tmp_path / "lines.jsonl"
    lines.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    assert collector.load_fixture(lines) == [payload]


def test_official_fetch_is_refused_without_a_read_only_channel():
    with pytest.raises(collector.CollectionRefused):
        collector.fetch_official(source="douyin")
    assert collector.fetch_official(source="douyin", reader=lambda: [{"a": 1}]) == [{"a": 1}]


def test_fixture_covers_the_four_intended_cases():
    corpus = load_corpus()
    uids = [j["uid"] for j in corpus["jobs"]]
    assert any(u.startswith("LRN_G1") for u in uids)
    assert any(u.startswith("LRN_G5") for u in uids)
    assert any(u.startswith("LRN_NODNA") for u in uids)
    flat = flat_snapshots(corpus)
    assert len(flat) == 16
