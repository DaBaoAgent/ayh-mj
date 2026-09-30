"""Phase 15.6 发布安全验收（含 §15.1 第 13 条：fake 适配器发布幂等）。

覆盖计划 §15.6：
  ① `real_publish=false` 时任何路径都不得真发（dry-run 不碰适配器、不落记录、不改状态）；
  ② `real_publish=true` 也必须逐个通过 artifact 完整性 / AI 声明 / claims 合规 / 配额 Gate；
  ③ 平台 auth 异常立即熔断该平台，不循环登录、不连续发布；一条都没发出去不许记 DONE；
  ④ 同一 external_id（`<uid>:<platform>`）幂等：重试不会重复发帖；
  ⑤ 自动评论命中价格/医疗/投诉红线 → 转人工，绝不调用 create_comment；
  ⑥ 平台验证码/风控/账号异常 → REQUIRE_HUMAN（暂停该平台 + 交人工，不做绕过）。

全部用 fake 适配器 / 临时 root：0 网络、0 真发、0 付费。
"""
from __future__ import annotations

import pytest

from lib import packaging
from lib.creative.structures import STORY_STRUCTURES
from lib.jobstore import JobState, store
from lib.orchestrator.errors import (
    CLAIM_UNMAPPED,
    PACKAGING_INCOMPLETE,
    PLATFORM_PAUSED,
    PUBLISH_AUTH,
    REQUIRE_HUMAN_PUBLISH,
)
from lib.orchestrator.publishing import (
    AI_DISCLOSURE_LABEL,
    AUTH_EXPIRED,
    PAUSED_STATUS,
    QUOTA_BLOCKED,
    SKIPPED,
    SUCCESS,
    PublishService,
)
from s6_publish.publish import CliPublishAdapter
from tests.p7_support import spec_for
from tests.p15_support import FakePublishAdapter

pytestmark = pytest.mark.integration

_BY_ID = {s["id"]: s for s in STORY_STRUCTURES}
_LINEAR_TO_READY = (JobState.RESEARCHING, JobState.SCRIPTING, JobState.PREFLIGHT,
                    JobState.GENERATING, JobState.QA, JobState.COMPOSING,
                    JobState.PACKAGING, JobState.READY)


# ── 装置 ──────────────────────────────────────────────────────────────
def _ready_job(uid: str, *, real: bool | None = True, platforms=("douyin",),
               config: bool = True) -> None:
    snapshot = ({"real_publish": real, "publish_platforms": list(platforms)}
                if config else None)
    store.create_job(goal="Phase 15.6 发布安全", uid=uid, config_snapshot=snapshot)
    for state in _LINEAR_TO_READY:
        store.transition(uid, state)


def _write_brief(root, uid: str, *, platforms=("douyin",), confirmable=None,
                 description: str | None = None, title: str | None = None) -> dict:
    doc = spec_for(_BY_ID["S_duo_conflict"], uid=uid)
    brief = packaging.build_brief(doc, uid=uid, platforms=list(platforms),
                                  disclosure_confirmable=confirmable or {},
                                  product_keywords=["电动轮椅", "轻便折叠"])
    if description is not None:
        brief["description"] = description
    if title is not None:
        brief["title"] = title
    packaging.save_brief(root, uid, brief)
    return brief


def _service(root, adapter, *, quota=None, marked=None) -> PublishService:
    return PublishService(store=store, adapter=adapter, root=root,
                          quota=quota or (lambda platform: (True, "OK")),
                          mark_published=(marked.append if marked is not None
                                          else (lambda p: None)),
                          sleep=lambda _s: None)


class _CliResult:
    """PostFlow CLI 的假输出（只看 returncode/stdout/stderr）。"""

    def __init__(self, text: str, returncode: int = 1) -> None:
        self.returncode = returncode
        self.stdout = text
        self.stderr = ""


# ── ① real_publish=false：任何路径都不许真发 ───────────────────────────
def test_dry_paths_never_reach_the_adapter(tmp_state, tmp_path):
    adapter = FakePublishAdapter()

    # (a) 显式 real=False（即使任务配置写着可以真发）
    uid_a = "P15DRY_A"
    _ready_job(uid_a, real=True)
    _write_brief(tmp_path, uid_a, confirmable={"douyin": True})
    out_a = _service(tmp_path, adapter).publish(uid_a, real=False)
    assert out_a["dry_run"] is True and out_a["ok"] is True
    assert store.get_job(uid_a)["status"] == JobState.READY

    # (b) 任务配置 real_publish=false，不传 real → 以配置为准
    uid_b = "P15DRY_B"
    _ready_job(uid_b, real=False)
    _write_brief(tmp_path, uid_b, confirmable={"douyin": True})
    out_b = _service(tmp_path, adapter).publish(uid_b)
    assert out_b["dry_run"] is True and out_b["ok"] is True
    assert store.get_job(uid_b)["status"] == JobState.READY

    # (c) 配置缺省（没有 real_publish 字段）→ 默认不真发
    uid_c = "P15DRY_C"
    _ready_job(uid_c, config=False)
    _write_brief(tmp_path, uid_c, confirmable={"douyin": True})
    out_c = _service(tmp_path, adapter).publish(uid_c)
    assert out_c["dry_run"] is True and out_c["ok"] is True
    assert store.get_job(uid_c)["status"] == JobState.READY

    # 三条路径合起来：适配器一次都没被调用，一条发布记录都没落
    assert adapter.calls == []
    for uid in (uid_a, uid_b, uid_c):
        assert store.list_publishes(uid) == []


def test_dry_run_still_reports_gate_failure_without_publishing(tmp_state, tmp_path):
    """演练也要如实报 Gate 结果（缺物料时 ok=False），但绝不真发。"""
    uid = "P15DRY_GATE"
    _ready_job(uid, real=False)
    adapter = FakePublishAdapter()
    out = _service(tmp_path, adapter).publish(uid)
    assert out["dry_run"] is True and out["ok"] is False
    assert out["error_code"] == PACKAGING_INCOMPLETE
    assert adapter.calls == []
    assert store.get_job(uid)["status"] == JobState.READY


# ── ② real_publish=true 也必须过每一道 Gate ────────────────────────────
def test_missing_artifact_blocks_before_any_publish(tmp_state, tmp_path):
    uid = "P15GATE_PKG"
    _ready_job(uid, real=True)
    adapter = FakePublishAdapter()
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False and out["error_code"] == PACKAGING_INCOMPLETE
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert adapter.calls == []


def test_ai_disclosure_without_draft_channel_requires_human(tmp_state, tmp_path):
    """声明无法确认且平台没有草稿通道（instagram）→ 只能人工，不许直发。"""
    uid = "P15GATE_DISC"
    _ready_job(uid, real=True, platforms=("instagram",))
    _write_brief(tmp_path, uid, platforms=("instagram",))
    adapter = FakePublishAdapter()
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False and out["error_code"] == REQUIRE_HUMAN_PUBLISH
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert adapter.calls == []


def test_unmapped_claim_in_publish_copy_is_blocked(tmp_state, tmp_path):
    """声明已确认（能走到 claims 门）时，描述里塞未登记参数必须被拦。"""
    uid = "P15GATE_CLAIM"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True},
                 description="一次能跑120公里，点开头像看同款")
    adapter = FakePublishAdapter()
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False and out["error_code"] == CLAIM_UNMAPPED
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert adapter.calls == []


def test_quota_block_stops_before_the_adapter(tmp_state, tmp_path):
    uid = "P15GATE_QUOTA"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True})
    adapter = FakePublishAdapter()
    out = _service(tmp_path, adapter, quota=lambda p: (False, "不在发布窗口")).publish(uid)
    assert adapter.calls == []
    assert out["results"][0]["status"] == QUOTA_BLOCKED
    assert store.list_publishes(uid)[0]["status"] == QUOTA_BLOCKED


def test_gate_pass_publishes_once_with_ai_disclosure_recorded(tmp_state, tmp_path):
    """全部门通过 → 真发一次，并且发布记录里必须带 AI 声明。"""
    uid = "P15GATE_OK"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True})
    adapter = FakePublishAdapter()
    marked: list[str] = []
    out = _service(tmp_path, adapter, marked=marked).publish(uid)
    assert out["ok"] is True and out["job_status"] == JobState.DONE
    assert adapter.platforms == ["douyin"] and marked == ["douyin"]
    record = store.list_publishes(uid)[0]
    assert record["status"] == SUCCESS
    assert record["external_id"] == f"{uid}:douyin"
    assert record["ai_disclosure"] == AI_DISCLOSURE_LABEL


# ── ③ auth 异常熔断：不循环、不重复、不伪成功 ──────────────────────────
def test_auth_expired_pauses_the_platform_and_never_loops(tmp_state, tmp_path):
    uid = "P15AUTH"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True})
    adapter = FakePublishAdapter(status=AUTH_EXPIRED, error="登录失效（fake）")
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False and out["error_code"] == PUBLISH_AUTH
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert packaging.pause_reason(tmp_path, "douyin")
    assert len(adapter.calls) == 1

    # 人工把任务放回 READY 再发：平台仍在暂停态 → 一次都不许再调适配器；
    # 而且这一轮一条都没发出去，绝不能记成 DONE。
    store.transition(uid, JobState.READY, message="人工处理凭据后回到 READY")
    again = _service(tmp_path, adapter).publish(uid)
    assert len(adapter.calls) == 1, "平台已熔断暂停却仍在调适配器"
    assert again["results"][0]["status"] == PAUSED_STATUS
    assert again["job_status"] == JobState.PAUSED
    assert again["ok"] is False and again["error_code"] == PLATFORM_PAUSED
    assert store.get_job(uid)["status"] == JobState.PAUSED
    assert store.list_publishes(uid)[0]["status"] == AUTH_EXPIRED


def test_platform_risk_control_is_recorded_as_require_human(tmp_state, tmp_path):
    """验证码/风控提示（真实适配器文本判定）→ REQUIRE_HUMAN + 暂停平台 + 不重试。"""
    uid = "P15RISK"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True})
    adapter = FakePublishAdapter(status="REQUIRE_HUMAN", error="账号异常：请完成验证码验证")
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False and out["error_code"] == REQUIRE_HUMAN_PUBLISH
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert packaging.pause_reason(tmp_path, "douyin")
    assert len(adapter.calls) == 1


def test_real_adapter_risk_signal_end_to_end_requires_human(tmp_state, tmp_path):
    """真实 CliPublishAdapter（假 CLI 输出）+ 真实 PublishService 的整链判定。"""
    uid = "P15RISK_E2E"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True})
    adapter = CliPublishAdapter(runner=lambda cmd: _CliResult("账号异常：请完成验证码验证"))
    out = _service(tmp_path, adapter).publish(uid)
    assert out["ok"] is False and out["error_code"] == REQUIRE_HUMAN_PUBLISH
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert packaging.pause_reason(tmp_path, "douyin")
    assert store.list_publishes(uid)[0]["status"] == "REQUIRE_HUMAN"


@pytest.mark.parametrize("text", [
    "发布失败：请求过于频繁，请完成验证码后重试",
    "账号异常，平台要求人工验证",
    "unusual activity detected, please complete human verification",
    "risk control triggered",
])
def test_cli_adapter_classifies_platform_risk_as_require_human(tmp_state, tmp_path, text):
    """真实 CliPublishAdapter 的文本判定：风控信号优先于凭据信号。"""
    adapter = CliPublishAdapter(runner=lambda cmd: _CliResult(text))
    res = adapter.publish(uid="U", job={"video_path": "v.mp4"}, brief={},
                          platform="douyin", copy={"title": "t", "description": "d",
                                                   "hashtags": []}, mode="direct")
    assert res["status"] == "REQUIRE_HUMAN", res


def test_cli_adapter_keeps_plain_failure_and_auth_failure_distinct(tmp_state, tmp_path):
    """普通失败仍是 FAILED；纯凭据失效仍是 AUTH_EXPIRED（不能被风控判定吃掉）。"""
    failed = CliPublishAdapter(runner=lambda cmd: _CliResult("上传失败：文件格式不支持"))
    res = failed.publish(uid="U", job={"video_path": "v.mp4"}, brief={}, platform="douyin",
                         copy={"title": "t", "description": "d", "hashtags": []},
                         mode="direct")
    assert res["status"] == "FAILED", res

    auth = CliPublishAdapter(runner=lambda cmd: _CliResult("未登录，请重新登录后重试"))
    res2 = auth.publish(uid="U", job={"video_path": "v.mp4"}, brief={}, platform="douyin",
                        copy={"title": "t", "description": "d", "hashtags": []},
                        mode="direct")
    assert res2["status"] == AUTH_EXPIRED, res2


def test_failed_platforms_do_not_erase_successful_ones(tmp_state, tmp_path):
    """按平台独立记录：一个平台失败不抹掉另一个平台的成功（也不许伪成功）。"""
    uid = "P15MULTI"
    _ready_job(uid, real=True, platforms=("douyin", "youtube"))
    _write_brief(tmp_path, uid, platforms=("douyin", "youtube"),
                 confirmable={"douyin": True, "youtube": True})
    adapter = FakePublishAdapter(platform_status={"youtube": "FAILED"})
    out = _service(tmp_path, adapter).publish(uid)
    by_platform = {r["platform"]: r for r in store.list_publishes(uid)}
    assert by_platform["douyin"]["status"] == SUCCESS
    assert by_platform["youtube"]["status"] == "FAILED"
    assert out["job_status"] == JobState.PAUSED


# ── ④ external_id 幂等（§15.1 第 13 条）───────────────────────────────
def test_same_external_id_is_never_posted_twice(tmp_state, tmp_path):
    uid = "P15IDEM"
    _ready_job(uid, real=True)
    _write_brief(tmp_path, uid, confirmable={"douyin": True})
    adapter = FakePublishAdapter()
    first = _service(tmp_path, adapter).publish(uid)
    assert first["ok"] is True and adapter.platforms == ["douyin"]
    assert len(store.list_publishes(uid)) == 1

    # 已经 DONE 的任务再发一次 → 直接拒绝（连 Gate 都不该再走）
    third = _service(tmp_path, adapter).publish(uid)
    assert third["ok"] is False and adapter.platforms == ["douyin"]

    # "发帖成功但状态没推进就崩了"：任务手上已有该平台的发帖记录，重试必须幂等跳过
    uid2 = "P15IDEM2"
    _ready_job(uid2, real=True)
    _write_brief(tmp_path, uid2, confirmable={"douyin": True})
    store.record_publish(uid2, "douyin", external_id=f"{uid2}:douyin",
                         status=SUCCESS, post_id="already-posted")
    again = _service(tmp_path, adapter).publish(uid2)
    assert adapter.platforms == ["douyin"], "重试产生第二次真实发布请求"
    assert again["results"][0]["status"] == SKIPPED
    assert again["job_status"] == JobState.DONE
    assert len(store.list_publishes(uid2)) == 1


# ── ⑤ 评论红线转人工，绝不自动回复 ────────────────────────────────────
@pytest.fixture()
def engage_no_network(tmp_state, tmp_path, monkeypatch):
    """s6_publish.engage 的外部依赖全换假（0 网络）；create_comment 记录调用。"""
    from lib.safety import EngageGuard
    from s6_publish import engage as mod

    sent: list[tuple] = []
    monkeypatch.setattr(mod, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(mod, "already_handled", lambda cid: False, raising=False)
    monkeypatch.setattr(mod, "record", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(mod, "build_guard",
                        lambda: EngageGuard({}, max_per_hour=10, cooldown_seconds=0,
                                            jitter_seconds=0, circuit_threshold=9),
                        raising=False)

    import s6_publish.uploadpost as up
    monkeypatch.setattr(up, "create_comment",
                        lambda *a, **k: sent.append(a) or {"ok": True}, raising=False)
    mod._sent = sent
    return mod


@pytest.mark.parametrize("text,kind", [
    ("这个多少钱，有优惠吗", "price"),
    ("我奶奶偏瘫能用这个康复治疗吗", "medical"),
    ("买了就坏，我要投诉退款", "complaint"),
])
def test_red_line_comments_go_to_human_and_are_never_answered(engage_no_network, monkeypatch,
                                                              text, kind):
    mod = engage_no_network
    kind_out, hit = mod.classify(text)
    assert kind_out == f"escalate_{kind}", (kind_out, hit)
    assert hit

    import s6_publish.uploadpost as up
    monkeypatch.setattr(up, "comments", lambda *a, **k: {"comments": [
        {"id": "c1", "text": text, "user": {"username": "alice"}}]}, raising=False)
    stats = mod.handle_comments("douyin", yes=True)
    assert stats["escalated"] == 1
    assert stats["replied"] == 0
    assert mod._sent == [], "红线评论被自动回复了"


def test_spam_comment_is_skipped_and_clean_comment_is_replied(engage_no_network, monkeypatch):
    mod = engage_no_network
    monkeypatch.setattr(mod, "gen_reply", lambda t, context="comment": "谢谢关注，这个能单手收纳",
                        raising=False)
    monkeypatch.setattr(mod, "review_reply", lambda reply, channel="engage": (True, ""),
                        raising=False)
    import s6_publish.uploadpost as up
    monkeypatch.setattr(up, "comments", lambda *a, **k: {"comments": [
        {"id": "c1", "text": "加微信推你便宜货源", "user": {"username": "spam"}},
        {"id": "c2", "text": "看着挺结实的", "user": {"username": "bob"}},
    ]}, raising=False)
    stats = mod.handle_comments("douyin", yes=True)
    assert stats["spam"] == 1 and stats["replied"] == 1
    assert len(mod._sent) == 1
