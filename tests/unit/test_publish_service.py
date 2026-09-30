"""Phase 10 单测 —— PublishService：READY → 发布 → DONE/PAUSED/BLOCKED。

对应计划 §Phase 10 必做任务 2/3/4/5/8 与验收：
  · fake provider 下可完整执行 READY → PUBLISHING → DONE；
  · 同一 job 重复调用 publish 不会产生第二次真实发布请求；
  · AUTH_EXPIRED 立即暂停该平台，不再反复发；
  · 发布失败按平台独立记录，一个平台失败不抹掉别的平台的成功；
  · real_publish=false 时只出计划，不改状态、不落记录。
"""
from __future__ import annotations

import pytest

from lib import packaging
from lib.creative.structures import STORY_STRUCTURES
from lib.jobstore import JobState, store
from lib.orchestrator.errors import (
    NOT_READY,
    PACKAGING_INCOMPLETE,
    PUBLISH_AUTH,
)
from lib.orchestrator.publishing import (
    AUTH_EXPIRED,
    DRAFT,
    FAILED,
    PAUSED_STATUS,
    QUOTA_BLOCKED,
    SKIPPED,
    SUCCESS,
    PublishService,
)
from tests.p7_support import spec_for

pytestmark = pytest.mark.unit

_BY_ID = {s["id"]: s for s in STORY_STRUCTURES}
_LINEAR_TO_READY = (JobState.RESEARCHING, JobState.SCRIPTING, JobState.PREFLIGHT,
                    JobState.GENERATING, JobState.QA, JobState.COMPOSING,
                    JobState.PACKAGING, JobState.READY)


class FakeAdapter:
    """假发布通道：记录调用，按平台返回预设状态。"""

    def __init__(self, results: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.results = dict(results or {})

    def publish(self, *, uid, job, brief, platform, copy, mode) -> dict:
        self.calls.append({"platform": platform, "mode": mode, "copy": copy})
        return dict(self.results.get(platform, {"status": SUCCESS, "post_id": f"{platform}-1"}))


def _ready_job(uid: str, *, real: bool = True, platforms=("douyin",),
               config: bool = True) -> None:
    snapshot = ({"real_publish": real, "publish_platforms": list(platforms)}
                if config else None)
    store.create_job(goal="发布测试", uid=uid, config_snapshot=snapshot)
    for state in _LINEAR_TO_READY:
        store.transition(uid, state)


def _write_brief(root, uid: str, *, platforms=("douyin",), confirmable=None) -> dict:
    doc = spec_for(_BY_ID["S_duo_conflict"], uid=uid)
    brief = packaging.build_brief(doc, uid=uid, platforms=list(platforms),
                                  disclosure_confirmable=confirmable or {},
                                  product_keywords=["电动轮椅", "轻便折叠"])
    packaging.save_brief(root, uid, brief)
    return brief


def _service(root, adapter, *, quota=None, marked=None) -> PublishService:
    return PublishService(
        store=store, adapter=adapter, root=root,
        quota=quota or (lambda platform: (True, "OK")),
        mark_published=(marked.append if marked is not None else (lambda p: None)),
        sleep=lambda _s: None,
    )


def test_dry_run_changes_nothing(tmp_state, tmp_path):
    uid = "P10DRY"
    _ready_job(uid, real=False)
    _write_brief(tmp_path, uid)
    adapter = FakeAdapter()
    out = _service(tmp_path, adapter).publish(uid)
    assert out["dry_run"] is True and out["ok"] is True
    assert adapter.calls == []
    assert store.get_job(uid)["status"] == JobState.READY
    assert store.list_publishes(uid) == []


def test_job_must_be_ready_to_publish(tmp_state, tmp_path):
    uid = "P10EARLY"
    store.create_job(goal="还没出片", uid=uid)
    out = _service(tmp_path, FakeAdapter()).publish(uid, real=True)
    assert out["ok"] is False and out["error_code"] == NOT_READY


def test_ready_publishes_through_publishing_to_done(tmp_state, tmp_path):
    uid = "P10OK"
    _ready_job(uid)
    _write_brief(tmp_path, uid)
    adapter = FakeAdapter()
    marked: list[str] = []
    out = _service(tmp_path, adapter, marked=marked).publish(uid)
    assert out["ok"] is True, out
    assert out["job_status"] == JobState.DONE
    assert [r["status"] for r in out["results"]] == [SUCCESS]
    assert marked == ["douyin"]
    assert store.get_job(uid)["status"] == JobState.DONE
    stages = [e.get("stage") for e in store.list_events(uid)]
    assert "publish" in stages
    records = store.list_publishes(uid)
    assert len(records) == 1
    assert records[0]["status"] == SUCCESS
    assert records[0]["external_id"] == f"{uid}:douyin"
    assert "AI" in str(records[0]["ai_disclosure"])


def test_republish_is_idempotent_and_never_calls_adapter_twice(tmp_state, tmp_path):
    """最危险的重试场景：发帖成功但 job 状态没来得及推进 → 重跑不能重复发帖。"""
    uid = "P10IDEM"
    _ready_job(uid)
    _write_brief(tmp_path, uid)
    store.record_publish(uid, "douyin", external_id=f"{uid}:douyin",
                         status=SUCCESS, post_id="already-posted")
    adapter = FakeAdapter()
    out = _service(tmp_path, adapter).publish(uid)
    assert adapter.calls == [], "幂等失败：已经发过的平台又被调了一次"
    assert out["results"][0]["status"] == SKIPPED
    assert out["job_status"] == JobState.DONE
    assert len(store.list_publishes(uid)) == 1


def test_second_publish_call_after_done_is_refused(tmp_state, tmp_path):
    uid = "P10DONE2"
    _ready_job(uid)
    _write_brief(tmp_path, uid)
    adapter = FakeAdapter()
    assert _service(tmp_path, adapter).publish(uid)["job_status"] == JobState.DONE
    again = _service(tmp_path, adapter).publish(uid)
    assert again["ok"] is False and again["error_code"] == NOT_READY
    assert len(adapter.calls) == 1


def test_partial_failure_goes_to_paused_with_per_platform_records(tmp_state, tmp_path):
    uid = "P10PART"
    _ready_job(uid, platforms=("douyin", "youtube"))
    _write_brief(tmp_path, uid, platforms=("douyin", "youtube"))
    adapter = FakeAdapter({"youtube": {"status": FAILED, "error": "boom"}})
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is True and out["job_status"] == JobState.PAUSED
    by_platform = {r["platform"]: r for r in store.list_publishes(uid)}
    assert by_platform["douyin"]["status"] == SUCCESS
    assert by_platform["youtube"]["status"] == FAILED


def test_all_failed_goes_to_blocked(tmp_state, tmp_path):
    uid = "P10ALLBAD"
    _ready_job(uid, platforms=("douyin",))
    _write_brief(tmp_path, uid)
    adapter = FakeAdapter({"douyin": {"status": AUTH_EXPIRED, "error": "登录失效"}})
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False
    assert out["job_status"] == JobState.BLOCKED
    assert out["error_code"] == PUBLISH_AUTH
    assert store.get_job(uid)["status"] == JobState.BLOCKED


def test_auth_expired_pauses_the_platform_for_good(tmp_state, tmp_path):
    uid = "P10AUTH"
    _ready_job(uid)
    _write_brief(tmp_path, uid)
    adapter = FakeAdapter({"douyin": {"status": AUTH_EXPIRED, "error": "登录失效"}})
    _service(tmp_path, adapter).publish(uid)
    assert packaging.pause_reason(tmp_path, "douyin")

    store.transition(uid, JobState.READY, message="人工处理凭据后回到 READY")
    again = _service(tmp_path, adapter).publish(uid)
    assert len(adapter.calls) == 1, "平台已暂停却仍在调适配器"
    assert again["results"][0]["status"] == PAUSED_STATUS
    assert "暂停" in again["results"][0]["reason"]

    # 人工确认后解除暂停 → 又能发（这条路径必须存在，否则就是死锁）
    packaging.resume_platform(tmp_path, "douyin")
    assert not packaging.pause_reason(tmp_path, "douyin")


def test_quota_block_is_recorded_per_platform(tmp_state, tmp_path):
    uid = "P10QUOTA"
    _ready_job(uid)
    _write_brief(tmp_path, uid)
    adapter = FakeAdapter()
    out = _service(tmp_path, adapter, quota=lambda p: (False, "不在发布窗口")).publish(uid)
    assert adapter.calls == []
    assert out["results"][0]["status"] == QUOTA_BLOCKED
    assert store.list_publishes(uid)[0]["status"] == QUOTA_BLOCKED


def test_missing_packaging_blocks_the_job(tmp_state, tmp_path):
    uid = "P10NOPKG"
    _ready_job(uid)
    out = _service(tmp_path, FakeAdapter()).publish(uid)
    assert out["ok"] is False
    assert out["error_code"] == PACKAGING_INCOMPLETE
    assert store.get_job(uid)["status"] == JobState.BLOCKED


def test_draft_outcome_still_counts_as_published(tmp_state, tmp_path):
    uid = "P10DRAFT"
    _ready_job(uid)
    _write_brief(tmp_path, uid)
    seen: list[str] = []
    adapter = FakeAdapter({"douyin": {"status": DRAFT, "detail": "已进草稿箱"}})
    out = _service(tmp_path, adapter, marked=seen).publish(uid)
    assert out["job_status"] == JobState.DONE
    assert adapter.calls[0]["mode"] == "draft"
    assert seen == ["douyin"]
    assert store.list_publishes(uid)[0]["status"] == DRAFT


def test_adapter_exception_does_not_kill_other_platforms(tmp_state, tmp_path):
    uid = "P10RAISE"
    _ready_job(uid, platforms=("douyin", "youtube"))
    _write_brief(tmp_path, uid, platforms=("douyin", "youtube"))

    class Boom(FakeAdapter):
        def publish(self, *, platform, **kw):
            if platform == "douyin":
                raise RuntimeError("通道炸了")
            return super().publish(platform=platform, **kw)

    out = _service(tmp_path, Boom()).publish(uid)
    by_platform = {r["platform"]: r for r in store.list_publishes(uid)}
    assert by_platform["douyin"]["status"] == FAILED
    assert by_platform["youtube"]["status"] == SUCCESS
    assert out["job_status"] == JobState.PAUSED
