"""Phase 12：任务台后端 API（webui.server）—— canonical 任务 + 结构化事件。

用 fastapi.testclient 在临时 state 上跑，不启动 Hermes 内核、不联网、不付费。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lib.jobstore import JobState, store
from lib.orchestrator import orchestrator
from tests import p12_support as S

pytestmark = pytest.mark.unit

DETAIL_KEYS = {
    "job", "summary", "creative", "qa", "evaluations", "attempts", "provider_tasks",
    "repairs", "repair_summary", "artifacts", "publishes", "performance", "events",
    "blocked",
}


@pytest.fixture()
def server_module(tmp_state, monkeypatch):
    from webui import server
    monkeypatch.setattr(server, "CONSOLE_STATE_FILE", tmp_state / "console.json", raising=False)
    monkeypatch.setattr(server, "STATE_DIR", tmp_state, raising=False)
    return server


@pytest.fixture()
def api(server_module, tmp_state):
    orchestrator.wait(timeout=30)
    client = TestClient(server_module.app)
    yield client
    orchestrator.wait(timeout=30)


# ── GET /api/jobs ──────────────────────────────────────────────────────

def test_list_jobs_returns_canonical_rows(api, tmp_state):
    S.make_job(store, "job_a", goal="目标甲", status=JobState.READY)
    S.make_job(store, "job_b", goal="目标乙", status=JobState.FAILED,
               error_code="VISUAL_QA_FAIL", error_stage="qa")
    res = api.get("/api/jobs")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert body["total"]["total"] == 2
    rows = {row["uid"]: row for row in body["jobs"]}
    assert rows["job_a"]["status"] == JobState.READY
    assert rows["job_a"]["actions"]["cancel"] is True
    assert rows["job_b"]["actions"]["retry"] is True
    assert rows["job_a"]["dry"] is True


def test_list_jobs_filters_by_status_and_query(api):
    S.make_job(store, "job_keep", goal="折叠车测评", status=JobState.READY)
    S.make_job(store, "job_drop", goal="别的选题", status=JobState.FAILED)
    by_status = api.get("/api/jobs", params={"status": "FAILED"}).json()
    assert [j["uid"] for j in by_status["jobs"]] == ["job_drop"]
    by_q = api.get("/api/jobs", params={"q": "折叠"}).json()
    assert [j["uid"] for j in by_q["jobs"]] == ["job_keep"]


def test_list_jobs_limit_is_bounded(api):
    assert api.get("/api/jobs", params={"limit": 0}).status_code == 422
    assert api.get("/api/jobs", params={"limit": 100}).status_code == 200


# ── GET /api/jobs/{uid} ────────────────────────────────────────────────

def test_job_detail_endpoints(api, tmp_state):
    S.make_job(store, "job_detail", goal="详情", status=JobState.GENERATING)
    for path in ("/api/jobs/job_detail", "/api/job/job_detail"):
        body = api.get(path).json()
        assert set(body) == DETAIL_KEYS, path
        assert body["job"]["uid"] == "job_detail"
        assert body["blocked"] is None


def test_job_detail_404(api):
    res = api.get("/api/jobs/job_missing")
    assert res.status_code == 404
    assert res.json()["error"] == "任务不存在"


def test_job_detail_blocked_explains_human_action(api):
    S.make_job(store, "job_blocked", status=JobState.BLOCKED,
               error_code="AI_DISCLOSURE_UNCONFIRMED", error_stage="publishing")
    body = api.get("/api/jobs/job_blocked").json()
    assert body["blocked"]["code"] == "AI_DISCLOSURE_UNCONFIRMED"
    assert body["blocked"]["human_action"]
    assert body["summary"]["actions"]["retry"] is True


# ── artifacts / events ─────────────────────────────────────────────────

def test_job_artifacts_and_404(api, tmp_state):
    S.make_job(store, "job_art", status=JobState.READY)
    S.add_artifact(store, "job_art", "final", "final.mp4", root=tmp_state.parent)
    body = api.get("/api/jobs/job_art/artifacts").json()
    assert body["count"] == 1 and body["artifacts"][0]["exists"] is True
    assert api.get("/api/jobs/nope/artifacts").status_code == 404


def test_job_events_since_and_404(api):
    S.make_job(store, "job_ev", status=JobState.GENERATING)
    first = api.get("/api/jobs/job_ev/events").json()
    assert first["count"] >= 2 and first["last_id"] == max(e["id"] for e in first["events"])
    store.add_event("job_ev", "note", "新增备注")
    tail = api.get("/api/jobs/job_ev/events", params={"since": first["last_id"]}).json()
    assert [e["message"] for e in tail["events"]] == ["新增备注"]
    assert api.get("/api/jobs/nope/events").status_code == 404


def test_sse_route_is_registered_before_uid_route(server_module):
    """路由按注册顺序匹配：`/api/jobs/events` 若注册晚了会被当成 uid="events"（实测 404）。"""
    paths = [getattr(route, "path", "") for route in server_module.app.routes]
    assert "/api/jobs/events" in paths
    assert paths.index("/api/jobs/events") < paths.index("/api/jobs/{uid}")


def test_sse_stream_emits_canonical_events_and_snapshot(server_module, tmp_state):
    """直接消费 SSE 生成器：canonical 事件帧 + 快照帧，帧格式固定（前端不再解析日志）。"""
    import asyncio

    S.make_job(store, "job_sse", status=JobState.GENERATING)

    async def take_frames(max_frames: int = 30):
        response = await server_module.api_jobs_events()
        agen = response.body_iterator
        frames: list[str] = []
        try:
            async for chunk in agen:
                frames.append(chunk)
                if "event: snapshot" in chunk or len(frames) >= max_frames:
                    break
        finally:
            await agen.aclose()
        return response, frames

    response, frames = asyncio.run(asyncio.wait_for(take_frames(), timeout=10))
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    body = "".join(frames)
    assert body.startswith("event: job\ndata: "), body[:200]
    assert "\nevent: snapshot\ndata: " in body, body[:200]

    job_frame = json.loads(body.split("\ndata: ", 1)[1].split("\n\n", 1)[0])
    assert job_frame["uid"] == "job_sse"
    snapshot = json.loads(body.split("event: snapshot\ndata: ", 1)[1].split("\n\n", 1)[0])
    assert snapshot["source_of_truth"] == "jobstore"
    assert "jobs_by_status" in snapshot


# ── cancel / retry / resume ────────────────────────────────────────────

def test_cancel_moves_job_to_cancelled(api, tmp_state):
    S.make_job(store, "job_cancel", status=JobState.READY)
    res = api.post("/api/jobs/job_cancel/cancel")
    assert res.status_code == 200 and res.json()["ok"] is True
    assert store.get_job("job_cancel")["status"] == JobState.CANCELLED


def test_cancel_unknown_and_terminal(api):
    assert api.post("/api/jobs/nope/cancel").status_code == 404
    S.make_job(store, "job_done", status=JobState.DONE)
    assert api.post("/api/jobs/job_done/cancel").status_code == 404


def test_retry_reruns_failed_job_to_ready(api, tmp_state):
    S.make_job(store, "job_retry", status=JobState.FAILED,
               error_code="VISUAL_QA_FAIL", error_stage="qa")
    res = api.post("/api/jobs/job_retry/retry")
    assert res.status_code == 200 and res.json()["ok"] is True
    orchestrator.wait(timeout=30, uids=["job_retry"])
    job = store.get_job("job_retry")
    assert job["status"] == JobState.READY
    assert job["error_code"] is None                       # retry 会清掉旧错误码
    assert api.get("/api/jobs/job_retry/events").json()["events"][-1]["type"] in (
        "status_change", "stage_end")


def test_retry_rejects_non_failed_job(api):
    S.make_job(store, "job_ok", status=JobState.READY)
    res = api.post("/api/jobs/job_ok/retry")
    assert res.status_code == 400
    assert res.json()["error_code"] == "JOB_NOT_RESUMABLE"
    assert api.post("/api/jobs/nope/retry").status_code == 400


def test_resume_continues_paused_job(api, tmp_state):
    S.make_job(store, "job_pause", status=JobState.PAUSED)
    res = api.post("/api/jobs/job_pause/resume")
    assert res.status_code == 200 and res.json()["ok"] is True
    orchestrator.wait(timeout=30, uids=["job_pause"])
    assert store.get_job("job_pause")["status"] == JobState.READY


def test_resume_rejects_terminal_job(api):
    S.make_job(store, "job_done2", status=JobState.DONE)
    res = api.post("/api/jobs/job_done2/resume")
    assert res.status_code == 400
    assert res.json()["error_code"] == "JOB_NOT_RESUMABLE"


# ── POST /api/jobs 与 /api/start 共用同一内核 ───────────────────────────

def test_create_job_endpoint_uses_same_kernel_as_start(api, server_module, monkeypatch):
    calls: list[dict] = []

    def fake_start_production(**kw):
        calls.append(kw)
        uid = f"job_fake_{len(calls)}"
        store.create_job(goal=kw.get("goal") or "", uid=uid,
                         config_snapshot={"dry_mode": bool(kw.get("dry"))})
        return {"ok": True, "jobs": [uid], "count": 1, "config": {"dry_mode": kw.get("dry")}}

    monkeypatch.setattr(server_module, "start_production", fake_start_production)
    created = api.post("/api/jobs", json={"goal": "目标甲", "dry": True})
    started = api.post("/api/start", json={"goal": "目标乙", "dry": True})
    assert created.status_code == started.status_code == 200
    assert [c["source"] for c in calls] == ["webui", "webui"]
    assert [c["dry"] for c in calls] == [True, True]
    body = created.json()
    assert body["ok"] is True and body["count"] == 1
    assert body["jobs"][0]["uid"] == "job_fake_1"
    assert body["jobs"][0]["dry"] is True


def test_create_job_validates_payload(api):
    assert api.post("/api/jobs", json={"stages": ["bogus"]}).status_code == 400
    assert api.post("/api/jobs", json={"stages": []}).status_code == 400


# ── settings / materials / health ──────────────────────────────────────

def test_settings_returns_runtime_and_ignored_reasons(api):
    res = api.post("/api/settings", json={"daily_target": 3, "real_publish": True,
                                          "bogus_key": 1, "gen_concurrency": 999})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["saved"] == {"daily_target": 3, "real_publish": True}
    assert body["ignored"]["bogus_key"] == "未知设置项"
    assert "范围" in body["ignored"]["gen_concurrency"]
    runtime = body["runtime"]
    assert runtime["daily_target"] == 3
    assert runtime["real_publish"] is True           # 保存值马上体现在运行时快照里
    assert runtime["dry_mode"] is False
    assert body["runtime_applies_to"]


def test_materials_endpoint_lists_produced_jobs(api, tmp_state):
    S.make_job(store, "job_mat", goal="物料", status=JobState.READY)
    S.make_job(store, "job_run2", goal="生成中", status=JobState.GENERATING)
    body = api.get("/api/materials").json()
    assert body["count"] == 1
    assert body["materials"][0]["uid"] == "job_mat"


def test_system_health_endpoint(api):
    body = api.get("/api/system/health").json()
    assert body["status"] in {"READY", "DEGRADED", "BLOCKED", "UNKNOWN"}
    assert isinstance(body["capabilities"], list)
