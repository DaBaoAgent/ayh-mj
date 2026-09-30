"""Phase 15.2 —— 故障恢复验收（逐项注入故障，验证不重复付费 / 不留伪成功）。

计划 §15.2 要求逐项注入：① 面板进程重启；② provider submit 后进程立即退出；
③ 网络查询超时；④ provider SUCCESS 后下载失败；⑤ SQLite busy / 短暂锁等待；
⑥ 磁盘空间不足；⑦ 缺字体 / 缺 ffmpeg / 缺 Upload-Post key。

每项的预期行为都写成断言：
  · 可自动恢复的走 RETRY/RESUME，绝不重复创建付费任务；
  · 能力缺失进 DEGRADED/BLOCKED，并给出人能照着做的修复提示；
  · 不可恢复错误停掉下游 stage，不产生伪成功 artifact；
  · 重启后 WebUI 只从 DB 读，不靠内存态。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from lib.creative import planner as planner_mod
from lib.creative.prescreen import needs_prescreen
from lib.jobstore import JobState, JobStore
from lib.jobstore import store as jobstore
from lib.orchestrator import RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import (
    CAPABILITY_BLOCKED,
    UNEXPECTED_ERROR,
    DownloadFailed,
    NetworkTransient,
)
from lib.orchestrator.generation import IdempotentGenerator
from tests import p15_support as S

pytestmark = pytest.mark.integration

GOAL = "Phase15恢复"


@pytest.fixture(autouse=True)
def _no_autodl(monkeypatch):
    return S.no_real_autodl(monkeypatch)


@pytest.fixture()
def lines(monkeypatch):
    return S.install_lines(monkeypatch)


def _low(tmp_state, *, count: int = 6):
    """挑一条低风险（不触发预筛）的自主规划稿，用于"正常能跑通"的恢复场景。"""
    planned = planner_mod.plan_missing(store=jobstore, daily_target=count, count=count,
                                       queue_dir=tmp_state / "queue_15s",
                                       state_dir=tmp_state, goal=GOAL)
    for pj in planned:
        doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
        if not needs_prescreen(doc):
            return pj
    raise AssertionError("这一批里必须有低风险稿子")


def _spec(pj) -> dict:
    return json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))


def _kinds(uid: str) -> list[str]:
    return [str(e["type"]) for e in jobstore.list_events(uid)]


def _generator(tmp_state, provider, *, retries: int = 2) -> IdempotentGenerator:
    return IdempotentGenerator(jobstore, provider, root=tmp_state, log=lambda _m: None,
                               sleep=lambda _s: None, poll_interval=1.0, max_wait=60.0,
                               download_retries=retries)


def _args(pj, tmp_state, doc: dict) -> dict:
    return {"uid": pj.uid, "prompt": doc["prompt"], "duration": 15,
            "resolution": doc.get("resolution") or "768p竖", "workflow": doc["workflow"],
            "fallback_workflows": [], "ref_images": [], "ref_audios": [],
            "out_path": tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4"}


def _run(tmp_state, pj, *, provider=None, **kwargs):
    provider = provider if provider is not None else S.new_provider()
    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider, **kwargs)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_repairs=0,
                    stages=list(stages_mod.STAGE_ORDER))
    res = orch.start(cfg, specs=[pj.spec_path], background=False)
    return orch, provider, res


# ── ① 面板重启：只认 DB，且不留运行句柄 ────────────────────────────────
def test_panel_restart_reads_the_db_and_leaves_no_running_handles(tmp_state, lines, monkeypatch):
    from fastapi.testclient import TestClient

    from webui import server

    pj = _low(tmp_state)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    provider = S.new_provider()
    orch, provider, res = _run(tmp_state, pj, provider=provider)
    assert res["ok"] is True, res
    assert jobstore.get_job(pj.uid)["status"] == JobState.READY
    assert orch.status()["running"] is False, "跑完不得残留运行句柄"

    # "重启"：新建实例（内存态全丢）+ 新建面板客户端，只能从 DB 恢复
    reborn = S.build_orchestrator(jobstore, tmp_state, provider=provider)
    assert reborn.recover_interrupted() == [], "已经 READY 的任务不该被当成被打断的任务"
    monkeypatch.setattr(server, "CONSOLE_STATE_FILE", tmp_state / "console.json",
                        raising=False)
    monkeypatch.setattr(server, "STATE_DIR", tmp_state, raising=False)
    client = TestClient(server.app)

    job = jobstore.get_job(pj.uid)
    view = client.get(f"/api/job/{pj.uid}").json()
    assert view["job"]["status"] == JobState.READY == job["status"]
    assert str(view["summary"]["cost_spent"]) == str(job["cost_spent"])
    assert len(view["attempts"]) == len(jobstore.list_attempts(pj.uid))
    assert len(view["events"]) == len(jobstore.list_events(pj.uid))
    assert view["blocked"] is None
    state_view = client.get("/api/state").json()
    assert state_view["run"]["source_of_truth"] == "jobstore", state_view["run"]


# ── ② provider submit 之后进程立即退出：重启只 query，不重提交 ──────────
def test_exit_right_after_submit_resumes_with_query_only(tmp_state, lines):
    pj = _low(tmp_state)
    doc = _spec(pj)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    out = tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4"

    provider = S.new_provider()
    provider.crash_on_query = True            # 提交成功、轮询时"进程没了"
    with pytest.raises(RuntimeError):
        _generator(tmp_state, provider).generate(**_args(pj, tmp_state, doc))

    rows = jobstore.list_provider_tasks(pj.uid, "generate")
    assert len(rows) == 1 and rows[0]["task_id"], rows
    assert rows[0]["status"] == "SUBMITTED", rows
    assert provider.submit_count == 1, "崩溃前那一次提交必须已经落库"
    assert not out.exists()

    # 重启：同一个 fingerprint 只能查到 task_id → 只 query、不重新提交
    provider.crash_on_query = False
    outcome = _generator(tmp_state, provider).generate(**_args(pj, tmp_state, doc))
    assert outcome.reused is True
    assert provider.submit_count == 1, "重启后必须只查询原任务，不产生第二次提交"
    assert provider.query_calls == 1
    assert out.is_file() and out.stat().st_size > 0
    kinds = _kinds(pj.uid)
    assert kinds.count("provider_submitted") == 1, kinds
    assert "provider_reused" in kinds, kinds


# ── ③ 网络查询超时：退避重试，不重复付费 ───────────────────────────────
def test_transient_query_timeout_retries_instead_of_resubmitting(tmp_state, lines):
    pj = _low(tmp_state)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    provider = S.new_provider()
    real_query = provider.query
    seen = {"n": 0}

    def flaky_query(task_id):
        seen["n"] += 1
        if seen["n"] <= 2:
            raise NetworkTransient("fake：查询超时", data={"attempt": seen["n"]})
        return real_query(task_id)

    provider.query = flaky_query
    _orch, provider, res = _run(tmp_state, pj, provider=provider,
                                poll_interval=1.0, max_wait=120.0)
    assert res["ok"] is True, res

    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.READY, (job["status"], job["error_code"])
    assert seen["n"] == 3, "两次瞬时错误后第三次必须成功，而不是放弃"
    assert provider.submit_count == 1, "网络抖动绝不能换来第二次付费提交"
    assert _kinds(pj.uid).count("provider_submitted") == 1


# ── ④ SUCCESS 之后下载失败：只重下，不重生成 ───────────────────────────
def test_download_failure_after_success_only_retries_download(tmp_state, lines):
    pj = _low(tmp_state)
    doc = _spec(pj)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    provider = S.new_provider()
    provider.download_fail_times = 9          # 超过 download_retries+1 → 最终仍失败
    out = tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4"

    with pytest.raises(DownloadFailed):
        _generator(tmp_state, provider, retries=2).generate(**_args(pj, tmp_state, doc))

    assert provider.submit_count == 1, "下载失败只许重下，绝不重新提交付费任务"
    assert provider.download_calls == 3, "1 次 + 2 次重下"
    assert not out.exists(), "下载没成功就不许留下伪产物"
    kinds = _kinds(pj.uid)
    assert kinds.count("download_retry") == 2, kinds
    assert "download_failed" in kinds and "provider_submitted" in kinds, kinds
    rows = jobstore.list_provider_tasks(pj.uid, "generate")
    assert rows and rows[0]["status"] == "FAILED", rows


# ── ⑤ SQLite busy：短暂锁等待要等，而不是秒失败 ─────────────────────────
def test_short_sqlite_lock_is_waited_out_not_lost(tmp_state):
    uid = jobstore.create_job(goal=GOAL, uid="BUSY-15")
    # 另一个连接在**它自己的线程**里持写锁 0.5s（sqlite 连接不可跨线程使用）
    held = threading.Event()
    done = threading.Event()

    def hold_locks():
        conn = sqlite3.connect(str(tmp_state / "pipeline.db"), timeout=30)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE jobs SET updated_at = updated_at WHERE uid = ?", (uid,))
        held.set()
        time.sleep(0.5)
        conn.commit()
        conn.close()
        done.set()

    thread = threading.Thread(target=hold_locks)
    thread.start()
    assert held.wait(5), "没能在 5s 内拿到写锁"
    try:
        t0 = time.time()
        jobstore.add_event(uid, "note", "busy 锁等待验收")
        waited = time.time() - t0
    finally:
        thread.join(timeout=30)
    assert done.is_set()
    assert waited >= 0.2, f"应该等锁（busy timeout）而不是秒失败：{waited:.3f}s"
    assert waited < 20, f"不该等到超时：{waited:.3f}s"
    assert any(e["type"] == "note" for e in jobstore.list_events(uid))


# ── ⑤′ SQLite 真锁死：不产生伪成功，DB 恢复后能续跑 ────────────────────
def test_hard_sqlite_error_stops_before_paying_and_stays_recoverable(tmp_state, lines,
                                                                    monkeypatch):
    pj = _low(tmp_state)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    provider = S.new_provider()

    real_find = JobStore.find_provider_task
    fired = {"n": 0}

    def locked_find(self, uid, fingerprint=None, **kw):
        if not fired["n"]:
            fired["n"] = 1
            raise sqlite3.OperationalError("database is locked")   # busy timeout 用尽
        return real_find(self, uid, fingerprint, **kw)

    monkeypatch.setattr(JobStore, "find_provider_task", locked_find)
    orch, provider, res = _run(tmp_state, pj, provider=provider)
    monkeypatch.setattr(JobStore, "find_provider_task", real_find)

    assert res["ok"] is True, res
    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.FAILED, job
    assert job["error_code"] == UNEXPECTED_ERROR, (job["error_code"], job["error"])
    assert provider.submit_attempts == 0 and provider.submit_count == 0, \
        "落库失败期间绝不允许有付费提交"
    assert float(job["cost_spent"] or 0.0) == 0.0
    assert jobstore.list_artifacts(pj.uid, "video") == []
    assert not (tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4").exists()
    assert "package" not in [a["stage"] for a in jobstore.list_attempts(pj.uid)]

    # DB 恢复 → retry 必须能跑完，且不重复提交
    resumed = orch.retry(pj.uid, background=False)
    assert resumed["ok"] is True, resumed
    assert jobstore.get_job(pj.uid)["status"] == JobState.READY
    assert provider.submit_count == 1


# ── ⑥ 磁盘空间不足：停下游，不留伪 artifact ────────────────────────────
def test_disk_full_stops_downstream_without_fake_artifact(tmp_state, lines):
    pj = _low(tmp_state)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    provider = S.new_provider()

    def no_space(task, out_path):
        raise OSError(28, "No space left on device")

    provider.download = no_space
    orch, provider, res = _run(tmp_state, pj, provider=provider)

    assert res["ok"] is True, res
    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.FAILED, job
    assert provider.submit_attempts == 1, "只许提交一次（后续 attempt 复用同一 task）"
    assert provider.submit_count == 1
    assert not (tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4").exists()
    assert jobstore.list_artifacts(pj.uid, "video") == []
    assert jobstore.list_artifacts(pj.uid, "final") == []
    stages_run = [a["stage"] for a in jobstore.list_attempts(pj.uid)]
    assert "qa" not in stages_run and "package" not in stages_run, stages_run


# ── ⑦ 能力缺失：DEGRADED/BLOCKED + 修复提示；缺能力不许跑下游 ───────────
def _cap(report: dict, name: str) -> dict:
    return next(c for c in report["capabilities"] if c["name"] == name)


def test_missing_capabilities_report_status_and_a_fix_without_crashing(tmp_state,
                                                                      monkeypatch):
    from tools import health_check as hc

    def missing(*_a, **_k):
        raise FileNotFoundError("ffmpeg 不在 PATH")

    monkeypatch.setattr("lib.tools.ffmpeg", missing, raising=False)
    monkeypatch.setattr("lib.tools.ffprobe", missing, raising=False)
    report = hc.run_health()
    assert report["status"] == hc.BLOCKED, report["status"]
    assert "ffmpeg" in report["blocking"], report["blocking"]
    ff = _cap(report, "ffmpeg")
    assert ff["status"] == hc.BLOCKED and ff["fix"], ff

    monkeypatch.setattr(hc, "check_ffmpeg", lambda: hc._cap("ffmpeg", hc.READY, "ok"))
    monkeypatch.setattr(
        hc, "check_font",
        lambda: hc._cap("font", hc.DEGRADED, "未找到字幕字体", required=False,
                        fix="把字体放进 assets/fonts 或设置 AYHMJ_FONTS_DIR"))
    monkeypatch.setattr(
        hc, "check_uploadpost",
        lambda: hc._cap("upload_post", hc.DEGRADED, "未配置", required=False,
                        fix="keyring set uploadpost api_key"))
    report = hc.run_health()
    assert report["status"] == hc.DEGRADED, report["status"]
    assert {"font", "upload_post"} <= set(report["degraded"]), report["degraded"]
    text = hc.format_report(report)
    assert "修复" in text and "assets/fonts" in text

    from fastapi.testclient import TestClient

    from webui import server
    monkeypatch.setattr(server, "STATE_DIR", tmp_state, raising=False)
    body = TestClient(server.app).get("/api/system/health").json()
    assert body["status"] in {hc.READY, hc.DEGRADED, hc.BLOCKED}
    assert {c["name"] for c in body["capabilities"]} >= {"ffmpeg", "font", "upload_post"}


def test_capability_blocked_stops_downstream_and_explains_the_fix(tmp_state, lines,
                                                                 monkeypatch):
    from fastapi.testclient import TestClient

    from webui import server

    pj = _low(tmp_state)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    ran: list[str] = []

    def no_ffmpeg(ctx):
        ran.append("compose")
        return StageResult.fail("compose", CAPABILITY_BLOCKED,
                                "缺 ffmpeg：装好或设置 FFMPEG_PATH 后重跑后期")

    orch = S.build_orchestrator(jobstore, tmp_state, provider=S.new_provider(),
                                stages_override={"compose": no_ffmpeg})
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_repairs=0,
                    stages=list(stages_mod.STAGE_ORDER))
    assert orch.start(cfg, specs=[pj.spec_path], background=False)["ok"] is True

    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == CAPABILITY_BLOCKED, (job["error_code"], job["error"])
    assert ran == ["compose"]
    stages_run = [a["stage"] for a in jobstore.list_attempts(pj.uid)]
    assert "package" not in stages_run, stages_run
    assert jobstore.list_artifacts(pj.uid, "final") == []

    monkeypatch.setattr(server, "STATE_DIR", tmp_state, raising=False)
    monkeypatch.setattr(server, "CONSOLE_STATE_FILE", tmp_state / "console.json",
                        raising=False)
    view = TestClient(server.app).get(f"/api/job/{pj.uid}").json()
    blocked = view["blocked"] or {}
    assert blocked.get("code") == CAPABILITY_BLOCKED, blocked
    assert "能力" in str(blocked.get("human_action") or ""), blocked
    assert blocked.get("next_action") == "REQUIRE_HUMAN", blocked
