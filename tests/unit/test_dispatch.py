"""队列派发缓存回归（Phase 2）。

queue JSON 只是 artifact/dispatch 缓存：登记幂等、内容变化可追溯，
删掉缓存不影响 JobStore 事实，且 WebUI 统计口径与 JobStore 完全一致。
"""
from __future__ import annotations

import json

import pytest

from lib import state as st
from lib.dispatch import spec_fingerprint, sync_queue
from lib.jobstore import JobState, store

pytestmark = pytest.mark.unit


def _write_spec(queue, uid: str, payload: dict) -> None:
    queue.mkdir(parents=True, exist_ok=True)
    (queue / f"{uid}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_sync_queue_registers_one_job_per_spec(tmp_state):
    queue = tmp_state / "queue_15s"
    _write_spec(queue, "T01", {"goal": "菜场试坐", "topic": "菜场"})
    _write_spec(queue, "T02", {"title": "邻里打脸"})

    mapped = sync_queue(queue)
    assert set(mapped) == {"T01", "T02"}

    job = store.get_job("T01")
    assert job["goal"] == "菜场试坐"
    assert job["status"] == JobState.PLANNING
    assert job["fingerprint"] == spec_fingerprint(queue / "T01.json")
    assert [a["type"] for a in store.list_artifacts("T01")] == ["spec"]


def test_sync_queue_is_idempotent(tmp_state):
    queue = tmp_state / "queue_15s"
    _write_spec(queue, "T01", {"goal": "g"})
    sync_queue(queue)
    sync_queue(queue)
    assert store.counts()["total"] == 1
    assert len(store.list_artifacts("T01")) == 1


def test_spec_change_is_tracked(tmp_state):
    queue = tmp_state / "queue_15s"
    _write_spec(queue, "T01", {"goal": "v1"})
    sync_queue(queue)
    _write_spec(queue, "T01", {"goal": "v2"})
    sync_queue(queue)

    assert len(store.list_artifacts("T01", "spec")) == 2
    assert any(e["type"] == "spec_updated" for e in store.list_events("T01"))


def test_removing_queue_keeps_jobstore_facts(tmp_state):
    import shutil

    queue = tmp_state / "queue_15s"
    _write_spec(queue, "T01", {"goal": "g"})
    sync_queue(queue)
    shutil.rmtree(queue)

    assert store.get_job("T01") is not None
    assert store.counts()["total"] == 1


def test_webui_stats_match_jobstore_counts(tmp_state):
    """WebUI 统计（/api/state 的 stats）与 JobStore 实际数量必须一致。"""
    queue = tmp_state / "queue_15s"
    for i in range(3):
        _write_spec(queue, f"J{i:02d}", {"goal": f"g{i}"})
    sync_queue(queue)
    store.transition("J00", JobState.RESEARCHING)

    stats = st.get_stats()
    counts = store.counts()
    assert stats["jobs_total"] == counts["total"] == 3
    assert sum(stats["jobs_by_status"].values()) == counts["total"]
