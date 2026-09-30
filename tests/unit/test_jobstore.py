"""canonical JobStore + 状态机回归（Phase 2）。

覆盖验收标准：
  · 任意任务可查询完整状态 / attempt / artifact / event；
  · 合法主线可一路走到 DONE 且全程可追溯；
  · 非法状态转换被拒绝并写明原因；
  · queue JSON 删除/重建不影响 JobStore 事实。
"""
from __future__ import annotations

import json

import pytest

from lib.jobstore import (
    InvalidTransition,
    JobState,
    can_transition,
    normalize_state,
    store,
)

pytestmark = pytest.mark.unit


def _advance(uid: str, target: str) -> None:
    for name in JobState.LINEAR[1:]:
        store.transition(uid, name)
        if name == target:
            return


def test_state_machine_walks_planning_to_done(tmp_state):
    uid = store.create_job(goal="今天生产 1 条")
    assert store.get_job(uid)["status"] == JobState.PLANNING

    _advance(uid, JobState.DONE)
    job = store.get_job(uid)
    assert job["status"] == JobState.DONE
    assert job["finished_at"]

    events = store.list_events(uid)
    chain = [e["to_status"] for e in events if e["type"] == "status_change"]
    assert chain == list(JobState.LINEAR[1:])


def test_illegal_transition_rejected_with_reason(tmp_state):
    uid = store.create_job()
    with pytest.raises(InvalidTransition) as exc:
        store.transition(uid, JobState.READY)
    msg = str(exc.value)
    assert "非法状态转换" in msg and "PLANNING" in msg and "READY" in msg
    # 被拒绝的转换不能留下任何状态变化
    assert store.get_job(uid)["status"] == JobState.PLANNING
    assert [e["type"] for e in store.list_events(uid)] == ["created"]


def test_terminal_state_is_closed(tmp_state):
    uid = store.create_job()
    _advance(uid, JobState.DONE)
    assert not can_transition(JobState.DONE, JobState.PLANNING)
    with pytest.raises(InvalidTransition):
        store.transition(uid, JobState.PLANNING)


def test_side_states_can_pause_and_resume(tmp_state):
    uid = store.create_job()
    store.transition(uid, JobState.PAUSED)
    assert store.get_job(uid)["status"] == JobState.PAUSED
    store.transition(uid, JobState.RESEARCHING)          # 恢复
    store.transition(uid, JobState.BLOCKED, error_code="AUTH_EXPIRED")
    assert store.get_job(uid)["error_code"] == "AUTH_EXPIRED"
    store.transition(uid, JobState.SCRIPTING)
    assert store.get_job(uid)["status"] == JobState.SCRIPTING


def test_legacy_aliases_normalize():
    assert normalize_state("pending") == JobState.PLANNING
    assert normalize_state("ready") == JobState.READY
    assert normalize_state("published") == JobState.DONE
    assert normalize_state("generate") == JobState.GENERATING
    with pytest.raises(ValueError):
        normalize_state("not-a-state")


def test_attempt_and_cost_tracking(tmp_state):
    uid = store.create_job()
    a1 = store.record_attempt(uid, "GENERATING", provider="autodl", workflow="h3",
                              fingerprint="fp-1")
    store.finish_attempt(a1, "FAILED", error_code="GENERATION_FAILED", cost=0.9, message="boom")
    a2 = store.record_attempt(uid, "GENERATING", provider="autodl", workflow="h3")
    store.finish_attempt(a2, "SUCCESS", cost=0.9)

    attempts = store.list_attempts(uid)
    assert [a["attempt_no"] for a in attempts] == [1, 2]
    assert attempts[0]["error_code"] == "GENERATION_FAILED"
    assert attempts[1]["status"] == "SUCCESS"

    assert store.add_cost(uid, 1.8) == pytest.approx(1.8)


def test_artifacts_are_versioned_and_hashed(tmp_state, tmp_path):
    uid = store.create_job()
    f1 = tmp_path / "spec_v1.json"
    f1.write_text('{"v": 1}', encoding="utf-8")
    f2 = tmp_path / "spec_v2.json"
    f2.write_text('{"v": 2}', encoding="utf-8")

    store.add_artifact(uid, "spec", f1, stage=JobState.SCRIPTING)
    store.add_artifact(uid, "spec", f2, stage=JobState.SCRIPTING)

    arts = store.list_artifacts(uid, "spec")
    assert [a["version"] for a in arts] == [1, 2]
    assert arts[0]["sha256"] and arts[0]["bytes"] == f1.stat().st_size
    assert arts[0]["path"] == str(f1)


def test_evaluations_and_publish_records_and_metrics(tmp_state):
    uid = store.create_job()
    store.add_evaluation(uid, "asr", score=0.93, passed=True, detail={"mismatch": []})
    store.add_evaluation(uid, "visual", score=0.4, passed=False, detail={"reason": "产品形变"})
    evals = store.list_evaluations(uid)
    assert evals[0]["detail"] == {"mismatch": []}
    assert evals[1]["passed"] == 0

    store.record_publish(uid, "douyin", post_id="p1", post_url="https://x/p1",
                         external_id="ext-1", status="PUBLISHED", ai_disclosure="declared")
    store.record_publish(uid, "douyin", post_id="p1", post_url="https://x/p1",
                         external_id="ext-1", status="PUBLISHED", ai_disclosure="declared")
    pubs = store.list_publishes(uid)
    assert len(pubs) == 1                      # 同 external_id 幂等
    assert pubs[0]["ai_disclosure"] == "declared"

    store.add_performance_metric(uid, "douyin", post_id="p1", views=1000, likes=None)
    with store._connect() as conn:
        row = conn.execute("SELECT views, likes FROM performance_metrics").fetchone()
    assert row[0] == 1000 and row[1] is None   # 缺失指标必须是 NULL，不能编造 0


def test_detail_returns_full_trace(tmp_state):
    uid = store.create_job(goal="goal-x")
    store.record_attempt(uid, "GENERATING")
    store.add_evaluation(uid, "asr", score=1.0, passed=True)
    store.add_event(uid, "note", "手动备注")
    store.transition(uid, JobState.RESEARCHING)
    d = store.detail(uid)
    assert d["job"]["uid"] == uid
    assert len(d["attempts"]) == 1
    assert len(d["evaluations"]) == 1
    assert len(d["events"]) >= 3               # created + note + status_change


def test_queue_json_is_only_a_cache(tmp_state):
    """queue JSON 删除后，JobStore 事实仍在（Phase 2 核心要求）。"""
    uid = store.create_job(goal="queue-cache-test")
    queue = tmp_state / "queue_15s"
    queue.mkdir(exist_ok=True)
    spec = queue / f"{uid}.json"
    spec.write_text(json.dumps({"uid": uid}), encoding="utf-8")

    spec.unlink()
    queue.rmdir()

    job = store.get_job(uid)
    assert job is not None and job["uid"] == uid
    assert store.counts()["total"] == 1
