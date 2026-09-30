"""Phase 10 集成 —— 打包 → 发布 Gate → canonical 发布（fake provider，0 付费 0 真发）。

覆盖计划 §Phase 10 验收：
  · fake provider 下可完整执行 READY → PUBLISHING → DONE；
  · 抖音 AI 声明无法确认时，系统拒绝 direct publish（只能草稿/人工）；
  · 发布标题/描述出现未登记 claim 时被 Compliance Gate 拦截；
  · 发布状态按平台写进 canonical `publish_records`，不再另立一套 jobs 状态。
"""
from __future__ import annotations

import json
import subprocess

import pytest

from lib import packaging
from lib.creative.structures import STORY_STRUCTURES
from lib.jobstore import JobState, store
from lib.orchestrator import RunConfig
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import CLAIM_UNMAPPED, PACKAGING_INCOMPLETE
from lib.orchestrator.models import StageContext
from lib.orchestrator.publishing import SKIPPED, SUCCESS, PublishService
from s6_publish.publish import CliPublishAdapter
from tests.p7_support import spec_for

pytestmark = pytest.mark.integration

UID = "P10PIPE"
_BY_ID = {s["id"]: s for s in STORY_STRUCTURES}
_LINEAR_TO_READY = (JobState.RESEARCHING, JobState.SCRIPTING, JobState.PREFLIGHT,
                    JobState.GENERATING, JobState.QA, JobState.COMPOSING,
                    JobState.PACKAGING, JobState.READY)


@pytest.fixture(autouse=True)
def _no_real_autodl(monkeypatch):
    """自动测试里任何真实的 AutoDL 提交都必须炸出来（Phase 15 硬约束）。"""
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


class RecordingAdapter:
    """假通道：记录调用（用来证明"发了一次、只发了一次"）。"""

    def __init__(self, results: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.results = dict(results or {})

    def publish(self, *, uid, job, brief, platform, copy, mode) -> dict:
        self.calls.append({"platform": platform, "mode": mode, "title": copy["title"],
                           "hashtags": copy["hashtags"]})
        return dict(self.results.get(platform, {"status": SUCCESS, "post_id": "p10"}))


def _root(tmp_path):
    return tmp_path / "repo"


def _ready_job(uid: str, *, platforms=("douyin",), real: bool = True) -> None:
    store.create_job(goal="Phase 10 集成", uid=uid,
                     config_snapshot={"real_publish": real,
                                      "publish_platforms": list(platforms)})
    for state in _LINEAR_TO_READY:
        store.transition(uid, state)


def _stage_package(root, uid: str, structure_id: str = "S_duo_conflict"):
    """跑真实的 stage_package：产出并保存 packaging artifact。"""
    workspace = packaging.workspace_dir(root, uid)
    workspace.mkdir(parents=True, exist_ok=True)
    final = workspace / "onetake_final.mp4"
    final.write_bytes(b"\x00" * 4096)

    spec_path = root / "state" / "queue_15s" / f"{uid}.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    doc = spec_for(_BY_ID[structure_id], uid=uid)
    spec_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    ctx = StageContext(uid=uid, stage="package", spec=spec_path,
                       config=RunConfig(publish_platforms=["douyin", "youtube"]),
                       workspace=workspace, root=root, store=store)
    return stages_mod.stage_package(ctx), workspace


def _service(root, adapter, *, quota=None) -> PublishService:
    return PublishService(store=store, adapter=adapter, root=root,
                          quota=quota or (lambda p: (True, "OK")),
                          mark_published=lambda p: None, sleep=lambda _s: None)


def test_package_artifact_then_publish_reaches_done(tmp_state, tmp_path, monkeypatch):
    """今天生产一条：包装 → 声明裁决 → 发布 → READY/PUBLISHING/DONE 全在 DB 里可追。"""
    root = _root(tmp_path)
    monkeypatch.setattr(packaging.state, "PAUSE_FILENAME", "publish_paused.json")

    result, workspace = _stage_package(root, UID)
    assert result.success, result.message
    assert result.metrics["packaging"] is True
    brief_path = workspace / "packaging.json"
    assert brief_path.is_file()
    artifact_types = [a["type"] for a in result.artifacts]
    assert "packaging" in artifact_types and "final" in artifact_types

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    assert len(brief["title_candidates"]) == 3
    assert set(brief["disclosure"]["mode"]) == {"douyin", "youtube"}
    # 默认无人确认过任何平台的 AI 声明 → 全部只能草稿
    assert set(brief["disclosure"]["mode"].values()) == {"draft"}

    _ready_job(UID, platforms=("douyin", "youtube"))
    adapter = RecordingAdapter()
    out = _service(root, adapter).publish(UID)

    assert out["ok"] is True and out["job_status"] == JobState.DONE
    assert [c["platform"] for c in adapter.calls] == ["douyin", "youtube"]
    assert {c["mode"] for c in adapter.calls} == {"draft"}
    assert store.get_job(UID)["status"] == JobState.DONE
    records = store.list_publishes(UID)
    assert {r["platform"] for r in records} == {"douyin", "youtube"}


def test_publish_uses_the_packaging_artifact_not_hardcoded_copy(tmp_state, tmp_path):
    """文案必须来自 packaging：手工改 artifact，发布出去的就是改后的内容。"""
    root = _root(tmp_path)
    _stage_package(root, UID)
    _ready_job(UID, platforms=("douyin",))
    brief = packaging.load_brief(root, UID)
    brief["title"] = "改成运营手选的那一句"
    brief["targets"] = [t for t in brief["targets"] if t["platform"] == "douyin"]
    packaging.save_brief(root, UID, brief)

    adapter = RecordingAdapter()
    _service(root, adapter).publish(UID, platforms=["douyin"])
    assert adapter.calls[0]["title"] == "改成运营手选的那一句"


def test_douyin_ai_disclosure_cannot_be_confirmed_so_no_direct_publish(tmp_state, tmp_path):
    """抖音声明无法确认 → 只能草稿；真实适配器在草稿参数未配置时**拒绝执行**，绝不直发。"""
    root = _root(tmp_path)
    _stage_package(root, UID)
    brief = packaging.load_brief(root, UID)

    out = packaging.publish_gate(brief, platforms=["douyin"])
    assert out.ok, out.message
    assert out.data["modes"]["douyin"] == "draft"      # 不是 direct

    ran: list[list[str]] = []

    def fake_runner(cmd):
        ran.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    adapter = CliPublishAdapter(runner=fake_runner)
    result = adapter.publish(uid=UID, job={"video_path": "x.mp4"}, brief=brief,
                             platform="douyin", copy=packaging.materialize(brief, "douyin"),
                             mode="draft")
    assert result["status"] == "FAILED"
    assert "草稿" in result["error"]
    assert ran == [], "草稿参数未确认却真的执行了 PostFlow 命令"


def test_unregistered_claim_in_publish_copy_is_blocked(tmp_state, tmp_path):
    """发布文案里出现未登记的产品数字 → Compliance Gate 拦截，job 转 BLOCKED。"""
    root = _root(tmp_path)
    _stage_package(root, UID)
    _ready_job(UID, platforms=("douyin",))

    brief = packaging.load_brief(root, UID)
    brief["title"] = "一次能跑120公里"
    packaging.save_brief(root, UID, brief)

    adapter = RecordingAdapter()
    out = _service(root, adapter).publish(UID)
    assert out["ok"] is False
    assert out["error_code"] == CLAIM_UNMAPPED
    assert adapter.calls == []
    assert store.get_job(UID)["status"] == JobState.BLOCKED


def test_publish_without_packaging_artifact_is_refused(tmp_state, tmp_path):
    root = _root(tmp_path)
    _ready_job(UID, platforms=("douyin",))
    out = _service(root, RecordingAdapter()).publish(UID)
    assert out["error_code"] == PACKAGING_INCOMPLETE
    assert store.get_job(UID)["status"] == JobState.BLOCKED


def test_repeated_publish_never_double_posts(tmp_state, tmp_path):
    """同一 job 重复 publish 不得产生第二次真实发布请求。"""
    root = _root(tmp_path)
    _stage_package(root, UID)
    _ready_job(UID, platforms=("douyin",))
    # 崩溃恢复场景：上一次发帖已成功、记录已落库，但进程在推进状态前挂了
    store.record_publish(UID, "douyin", external_id=f"{UID}:douyin",
                         status=SUCCESS, post_id="already-posted")
    adapter = RecordingAdapter()
    out = _service(root, adapter).publish(UID, platforms=["douyin"])
    assert adapter.calls == [], "重试把已发布的平台又发了一次"
    assert out["results"][0]["status"] == SKIPPED
    assert out["job_status"] == JobState.DONE
    assert len(store.list_publishes(UID)) == 1
