"""lib.state 兼容门面回归（Phase 0 建立，Phase 2 对齐 canonical 状态机）。"""
from __future__ import annotations

import pytest

from lib import state as st
from lib.jobstore import JobState, store

pytestmark = pytest.mark.unit


def _advance(uid: str, target: str) -> None:
    """沿主线逐个状态推进到 target（状态机只允许一步一步向前）。"""
    for name in JobState.LINEAR[1:]:
        store.transition(uid, name)
        if name == target:
            return


def test_create_and_get_job(tmp_state):
    uid = st.create_job()
    job = st.get_job(uid)
    assert job is not None
    assert job["uid"] == uid
    assert job["status"] == JobState.PLANNING


def test_create_job_uid_is_unique(tmp_state):
    uids = {st.create_job() for _ in range(50)}
    assert len(uids) == 50


def test_update_job_field_whitelist(tmp_state):
    uid = st.create_job()
    st.update_job(uid, status="researching", duration=15.0)
    assert st.get_job(uid)["status"] == JobState.RESEARCHING
    assert st.get_job(uid)["duration"] == 15.0
    with pytest.raises(ValueError):
        st.update_job(uid, not_a_real_column=1)
    with pytest.raises(ValueError):
        store.set_fields(uid, status=JobState.READY)   # 状态禁止走 set_fields


def test_list_jobs_filters_by_status(tmp_state):
    a = st.create_job()
    st.create_job()
    st.update_job(a, status="failed")
    failed = st.list_jobs("failed")
    assert [j["uid"] for j in failed] == [a]
    assert failed[0]["status"] == JobState.FAILED


def test_get_stats_counts(tmp_state):
    a = st.create_job()
    _advance(a, JobState.READY)
    stats = st.get_stats()
    assert stats["jobs_total"] >= 1
    assert stats["jobs_ready"] >= 1
    assert stats["jobs_by_status"][JobState.READY] >= 1


def test_init_db_is_idempotent(tmp_state):
    st.init_db()
    st.init_db()
    assert st.get_stats()["jobs_total"] == 0
