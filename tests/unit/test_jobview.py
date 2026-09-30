"""Phase 12：任务台投影层（webui.jobview）—— 只读、不猜、不编造。"""
from __future__ import annotations

import json

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator.errors import human_action_hint, is_retryable, repair_action_for
from tests import p12_support as S
from webui import jobview


@pytest.fixture()
def out_dir(tmp_state):
    path = tmp_state.parent / "out"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── blocked：为什么需要人工 ─────────────────────────────────────────────

def test_blocked_block_none_while_job_is_still_running(tmp_state, out_dir):
    S.make_job(store, "job_run", status=JobState.GENERATING)
    detail = jobview.detail_view(store, "job_run", state_dir=tmp_state, out_dir=out_dir)
    assert detail["blocked"] is None


def test_blocked_block_explains_failed_job(tmp_state, out_dir):
    S.make_job(store, "job_fail", goal="失败样本", status=JobState.FAILED,
               error_code="VISUAL_QA_FAIL", error_stage="qa")
    detail = jobview.detail_view(store, "job_fail", state_dir=tmp_state, out_dir=out_dir)
    blocked = detail["blocked"]
    assert blocked["code"] == "VISUAL_QA_FAIL"
    assert blocked["stage"] == "qa"
    assert blocked["human_action"] == human_action_hint("VISUAL_QA_FAIL", blocked["message"])
    assert blocked["next_action"] == repair_action_for("VISUAL_QA_FAIL")
    assert blocked["retryable"] is is_retryable("VISUAL_QA_FAIL")
    assert "重出" in blocked["human_action"]          # 说人话，不是只丢错误码


def test_blocked_block_for_publish_gate_says_human(tmp_state, out_dir):
    S.make_job(store, "job_block", status=JobState.BLOCKED,
               error_code="AI_DISCLOSURE_UNCONFIRMED", error_stage="publishing")
    blocked = jobview.detail_view(store, "job_block", state_dir=tmp_state,
                                  out_dir=out_dir)["blocked"]
    assert blocked["code"] == "AI_DISCLOSURE_UNCONFIRMED"
    assert blocked["human_action"] == human_action_hint("AI_DISCLOSURE_UNCONFIRMED")
    assert "人工" in blocked["human_action"] or "草稿" in blocked["human_action"]


def test_blocked_block_reads_code_from_event_data(tmp_state, out_dir):
    """orchestrator 把错误码写在 stage_failed 事件的 data 里；job.error_code 被清空也要能读到。"""
    S.make_job(store, "job_data", status=JobState.BLOCKED,
               error_code="PUBLISH_AUTH", error_stage="publishing")
    store.set_fields("job_data", error_code=None)
    blocked = jobview.detail_view(store, "job_data", state_dir=tmp_state,
                                  out_dir=out_dir)["blocked"]
    assert blocked["code"] == "PUBLISH_AUTH"


def test_blocked_block_falls_back_to_repair_code(tmp_state, out_dir):
    S.make_job(store, "job_repair", status=JobState.FAILED)
    S.add_repair(store, "job_repair", error_code="PRODUCT_DEFORMED", action="REGENERATE_SHOT")
    blocked = jobview.detail_view(store, "job_repair", state_dir=tmp_state,
                                  out_dir=out_dir)["blocked"]
    assert blocked["code"] == "PRODUCT_DEFORMED"


# ── job_summary：动作布尔来自状态机白名单 ────────────────────────────────

def test_job_summary_actions_match_state_matrix():
    for status in JobState.ALL:
        row = jobview.job_summary({"uid": "u", "status": status})
        assert row["actions"]["cancel"] is (status in jobview.CANCELLABLE)
        assert row["actions"]["retry"] is (status in jobview.RETRYABLE)
        assert row["actions"]["resume"] is (status in jobview.RESUMABLE)


def test_job_summary_terminal_states_have_no_actions():
    done = jobview.job_summary({"uid": "u", "status": JobState.DONE})
    assert done["actions"] == {"cancel": False, "retry": False, "resume": False}


def test_job_summary_dry_comes_from_config_snapshot():
    on = jobview.job_summary({"uid": "u", "status": JobState.READY,
                              "config_snapshot": json.dumps({"dry_mode": True})})
    off = jobview.job_summary({"uid": "u", "status": JobState.READY,
                               "config_snapshot": json.dumps({"dry_mode": False})})
    none = jobview.job_summary({"uid": "u", "status": JobState.READY})
    assert on["dry"] is True and off["dry"] is False and none["dry"] is None


def test_job_summary_cost_and_unknown_fields_are_not_invented():
    row = jobview.job_summary({"uid": "u", "status": JobState.PLANNING})
    assert row["cost_spent"] is None and row["cost_estimate"] is None
    assert row["error_code"] == "" and row["stage"] == ""


# ── qa_view ────────────────────────────────────────────────────────────

def test_qa_view_missing_records_does_not_invent_scores():
    view = jobview.qa_view([])
    assert view["count"] == 0
    assert view["latest_score"] is None and view["min_score"] is None
    assert view["latest_passed"] is None and view["latest_kind"] is None


def test_qa_view_ignores_non_qa_kinds_and_takes_min():
    rows = [
        {"kind": "prescreen", "score": 0.1, "passed": False},
        {"kind": "qa_critic", "score": 0.8, "passed": True},
        {"kind": "qa_critic", "score": 0.55, "passed": False},
    ]
    view = jobview.qa_view(rows)
    assert view["count"] == 2
    assert view["latest_score"] == 0.55 and view["latest_passed"] is False
    assert view["min_score"] == 0.55


# ── detail_view / artifacts_view / events_view ──────────────────────────

def test_detail_view_unknown_job_returns_none(tmp_state, out_dir):
    assert jobview.detail_view(store, "nope", state_dir=tmp_state, out_dir=out_dir) is None


def test_detail_view_shape_and_creative_dna(tmp_state, out_dir):
    S.make_job(store, "job_detail", goal="详情样本", status=JobState.READY)
    S.write_dna(tmp_state, "job_detail", "S_duo_conflict", genre="G7")
    S.add_artifact(store, "job_detail", "final", "final.mp4", root=tmp_state.parent)
    S.add_qa(store, "job_detail", score=0.93)
    S.add_attempt(store, "job_detail", "generate", cost=0.7)
    S.add_repair(store, "job_detail", error_code="VISUAL_QA_FAIL", cost=0.3)
    S.add_publish(store, "job_detail", "douyin", status="DRAFT")
    S.add_performance(store, "job_detail", "douyin", views=1000, completion=0.4)

    detail = jobview.detail_view(store, "job_detail", state_dir=tmp_state, out_dir=out_dir)
    assert set(detail) == {
        "job", "summary", "creative", "qa", "evaluations", "attempts", "provider_tasks",
        "repairs", "repair_summary", "artifacts", "publishes", "performance", "events",
        "blocked",
    }
    assert detail["creative"]["dna"]["genre"] == "G7"
    assert detail["creative"]["structure"] == "S_duo_conflict"
    assert detail["qa"]["latest_score"] == 0.93
    assert detail["repair_summary"]["count"] == 1
    assert detail["repair_summary"]["cost"] == 0.3
    assert detail["blocked"] is None
    assert detail["attempts"][-1]["is_current"] is True
    assert detail["artifacts"][0]["exists"] is True
    assert detail["performance"][0]["metric_count"] == 2     # views + completion


def test_detail_view_without_dna_is_none_not_fabricated(tmp_state, out_dir):
    S.make_job(store, "job_nodna", status=JobState.READY)
    detail = jobview.detail_view(store, "job_nodna", state_dir=tmp_state, out_dir=out_dir)
    assert detail["creative"] is None


def test_load_creative_bad_json_is_none(tmp_state):
    path = tmp_state / "creative" / "dna_job_bad.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert jobview.load_creative(tmp_state, "job_bad") is None


def test_artifacts_view_reports_missing_files(tmp_state, out_dir):
    S.make_job(store, "job_art", status=JobState.READY)
    S.add_artifact(store, "job_art", "final", "ok.mp4", root=tmp_state.parent)
    store.add_artifact("job_art", "packaging", tmp_state / "gone.json")
    view = jobview.artifacts_view(store, "job_art")
    assert view["count"] == 2
    by_type = {a["type"]: a for a in view["artifacts"]}
    assert by_type["final"]["exists"] is True and by_type["final"]["name"] == "ok.mp4"
    assert by_type["packaging"]["exists"] is False
    assert jobview.artifacts_view(store, "nope")["error"] == "任务不存在"


def test_events_view_since_and_last_id(tmp_state):
    S.make_job(store, "job_ev", status=JobState.GENERATING)
    store.add_event("job_ev", "note", "第一条备注")
    store.add_event("job_ev", "note", "第二条备注")
    full = jobview.events_view(store, "job_ev")
    assert full["count"] == len(full["events"]) >= 3
    assert full["last_id"] == max(e["id"] for e in full["events"])
    tail = jobview.events_view(store, "job_ev", since=full["events"][-2]["id"])
    assert [e["message"] for e in tail["events"]][-1] == "第二条备注"
    assert jobview.events_view(store, "nope")["error"] == "任务不存在"


# ── materials：成片区 ───────────────────────────────────────────────────

def test_materials_only_lists_produced_states(tmp_state, out_dir):
    S.make_job(store, "job_ready", goal="已出片", status=JobState.READY)
    S.make_job(store, "job_gen", goal="还在生成", status=JobState.GENERATING)
    S.make_job(store, "job_done", goal="已发布", status=JobState.DONE)
    items = jobview.materials(store, state_dir=tmp_state, out_dir=out_dir)
    uids = [m["uid"] for m in items]
    assert "job_ready" in uids and "job_done" in uids
    assert "job_gen" not in uids
    assert all(m["status"] in jobview.MATERIAL_STATES for m in items)


def test_material_card_carries_video_qa_title_publish_performance(tmp_state, out_dir):
    S.make_job(store, "job_card", goal="物料卡", status=JobState.READY, cost_spent=1.5)
    S.add_artifact(store, "job_card", "final", "card.mp4", root=tmp_state.parent)
    packaging = {"chosen_title": "标题A", "cover_text": "封面A", "hashtags": ["#a", "#b"]}
    packaging_path = tmp_state / "packaging_job_card.json"
    packaging_path.write_text(json.dumps(packaging, ensure_ascii=False), encoding="utf-8")
    store.add_artifact("job_card", "packaging", packaging_path)
    S.add_qa(store, "job_card", score=0.88, passed=True)
    S.add_publish(store, "job_card", "douyin", status="DRAFT", external_id="d1")
    S.add_performance(store, "job_card", "douyin", views=10, likes=2)

    card = jobview.materials(store, state_dir=tmp_state, out_dir=out_dir, limit=5)[0]
    assert card["video"].endswith("card.mp4")
    assert card["video_url"] == "/media/card.mp4"
    assert card["qa"]["latest_score"] == 0.88
    assert card["title"] == "标题A"
    assert card["cover"] == "封面A"
    assert card["hashtags"] == ["#a", "#b"]
    assert card["publish"][0]["status"] == "DRAFT"
    assert card["performance"]["metric_count"] == 2
    assert card["blocked"] is None
    assert card["cost_spent"] == 1.5


def test_material_card_blocked_state_explains_why(tmp_state, out_dir):
    S.make_job(store, "job_cardblock", status=JobState.BLOCKED,
               error_code="AI_DISCLOSURE_UNCONFIRMED", error_stage="publishing")
    card = jobview.materials(store, state_dir=tmp_state, out_dir=out_dir)[0]
    assert card["blocked"]["code"] == "AI_DISCLOSURE_UNCONFIRMED"
    assert card["blocked"]["human_action"]


def test_media_url_only_for_files_under_out(tmp_state, out_dir):
    outside = tmp_state / "elsewhere.mp4"
    outside.write_bytes(b"x")
    assert jobview._media_url(out_dir, str(outside)) == ""
    assert jobview._media_url(out_dir, "") == ""
    assert jobview._media_url(None, "/whatever.mp4") == ""


def test_perf_view_keeps_missing_metrics_as_none():
    row = {"platform": "douyin", "views": 0, "likes": None}
    view = jobview.perf_view(row)
    assert view["metric_count"] == 1                # 0 是真实数值，None 才是"平台没给"
    assert view["metrics"]["views"] == 0
    assert view["metrics"]["likes"] is None
    assert view["metrics"]["completion"] is None


def test_material_uses_latest_performance_snapshot(tmp_state, out_dir):
    S.make_job(store, "job_perf", status=JobState.READY)
    S.add_performance(store, "job_perf", "douyin", snapshot_time="2026-09-01T00:00:00", views=1)
    S.add_performance(store, "job_perf", "douyin", snapshot_time="2026-09-29T00:00:00", views=99)
    card = jobview.materials(store, state_dir=tmp_state, out_dir=out_dir)[0]
    assert card["performance"]["metrics"]["views"] == 99
