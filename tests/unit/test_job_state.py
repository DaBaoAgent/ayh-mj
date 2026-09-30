"""lib.state 基线回归（Phase 0）。"""
from __future__ import annotations

import pytest

from lib import state as st

pytestmark = pytest.mark.unit


def test_create_and_get_job(tmp_state):
    uid = st.create_job()
    job = st.get_job(uid)
    assert job is not None
    assert job["uid"] == uid
    assert job["status"] == "pending"


def test_create_job_uid_is_unique(tmp_state):
    uids = {st.create_job() for _ in range(50)}
    assert len(uids) == 50


def test_update_job_field_whitelist(tmp_state):
    uid = st.create_job()
    st.update_job(uid, status="ready", duration=15.0)
    assert st.get_job(uid)["status"] == "ready"
    with pytest.raises(ValueError):
        st.update_job(uid, status="ready", not_a_real_column=1)


def test_list_jobs_filters_by_status(tmp_state):
    a = st.create_job()
    st.create_job()
    st.update_job(a, status="failed")
    failed = st.list_jobs("failed")
    assert [j["uid"] for j in failed] == [a]


def test_get_stats_counts(tmp_state):
    a = st.create_job()
    st.update_job(a, status="ready")
    stats = st.get_stats()
    assert stats["jobs_total"] >= 1
    assert stats["jobs_ready"] >= 1


def test_init_db_is_idempotent(tmp_state):
    st.init_db()
    st.init_db()
    assert st.get_stats()["jobs_total"] == 0
