"""Phase 15.1 —— 无付费全链验收（fake provider + fixture media）。

覆盖计划 §15.1 里"主链本身"的那几条：
  · 空队列 + daily_target=5 起步，Planner 自主选题并自动建 5 个 job（不靠人工预放 spec）；
  · 5/5 收敛到预期终态（READY，或设计内的 BLOCKED）；
  · 无重复 provider submit、无残留运行句柄、无未捕获异常；
  · Research / CreativeDNA / StorySpec / 编译 prompt 全部可查询；
  · genre / hook_type / shot_pattern 三维确实有结构差异；
  · Claims Gate 能把注入的虚假参数挡在付费生成之前；
  · 后期只认一份 canonical transcript；
  · 每条 READY 都有完整 packaging（标题/描述/claim ids/AI 声明）；
  · WebUI 读到的状态/attempt/cost/QA/repair 与 JobStore 逐项一致。

装置说明见 `tests/p15_support.py`：只替换**外部输入**（台词稿 / 观感证据 / 渲染），
产线的判定逻辑（Planner、各道门禁、Critic、RepairEngine、状态机）全部真实执行。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.jobstore import JobState
from lib.jobstore import store as jobstore
from lib.orchestrator import RunConfig
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import CLAIM_UNMAPPED, PRESCREEN_REQUIRED
from lib.post import transcript as transcript_mod
from tests import p15_support as S

pytestmark = pytest.mark.integration

GOAL = "Phase15自主全链"
REACHED = {JobState.READY, JobState.DONE}
SETTLED = REACHED | {JobState.BLOCKED, JobState.PAUSED}
# plan 阶段必须能查到的创意产物（§15.1-3）
PLAN_ARTIFACTS = ("spec", "research", "creative_dna", "creative_scores", "claims",
                  "dialogue_check")
# 出片后必须齐备的产物
VIDEO_ARTIFACTS = ("video", "qa_report", "qa_report_md", "final", "packaging")


@pytest.fixture(autouse=True)
def _no_autodl(monkeypatch):
    """Phase 15 硬约束：自动测试里任何真实的 AutoDL 提交都必须炸出来。"""
    return S.no_real_autodl(monkeypatch)


def _isolate_state(mp, state: Path) -> None:
    """与 conftest.tmp_state 同口径；可在 module 级 fixture 里手动开关。"""
    from lib import state as state_mod

    mp.setattr(state_mod, "DB_PATH", state / "pipeline.db", raising=False)
    state_mod.init_db()
    import lib.angles as angles
    import lib.creative.cast_groups as cast_groups
    import lib.genres as genres
    import lib.ideas as ideas
    import lib.products as products

    mp.setattr(ideas, "IDEAS_STATE", state / "used_ideas.json", raising=False)
    mp.setattr(genres, "STATE", state / "genres_used.json", raising=False)
    mp.setattr(angles, "STATE", state / "story_angles_used.json", raising=False)
    mp.setattr(products, "STATE", state / "sales_points_used.json", raising=False)
    mp.setattr(cast_groups, "GROUPS_STATE", state / "groups_used.json", raising=False)


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """整条自主全链只跑一次（较慢），下面所有用例共享这一次运行的事实。"""
    mp = pytest.MonkeyPatch()
    state = tmp_path_factory.mktemp("p15_chain") / "state"
    state.mkdir(parents=True, exist_ok=True)
    _isolate_state(mp, state)
    S.no_real_autodl(mp)
    S.install_lines(mp)

    queue = state / "queue_15s"
    assert not queue.exists(), "验收前提：空队列起步（没有人工预放 spec）"

    provider = S.new_provider()
    orch = S.build_orchestrator(jobstore, state, provider=provider)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=5, max_repairs=2,
                    stages=list(stages_mod.STAGE_ORDER))
    res = orch.start(cfg, background=False)
    try:
        yield {"res": res, "uids": list(res.get("jobs") or []), "state": state,
               "queue": queue, "provider": provider, "orch": orch}
    finally:
        mp.undo()


def _status(uid: str) -> str:
    return str((jobstore.get_job(uid) or {}).get("status") or "")


def _uids_with(chain, statuses) -> list[str]:
    return [u for u in chain["uids"] if _status(u) in statuses]


def _plan_metrics(uid: str) -> dict:
    for event in jobstore.list_events(uid):
        if event.get("type") == "stage_end" and event.get("stage") == "plan":
            return dict((event.get("data") or {}).get("metrics") or {})
    return {}


def _artifacts(uid: str) -> dict[str, str]:
    return {str(a["type"]): str(a.get("path") or "") for a in jobstore.list_artifacts(uid)}


# ── ① 自主规划：空队列起步，5 个 job 由 Planner 现造 ────────────────────
def test_autonomous_chain_plans_five_jobs_without_manual_specs(chain):
    res = chain["res"]
    assert res["ok"] is True, res
    assert res["count"] == 5, res
    assert len(chain["uids"]) == 5 and len(set(chain["uids"])) == 5, chain["uids"]
    for uid in chain["uids"]:
        # Planner 生成的 uid 形如 job_<day>_<goal slug>_<stamp>_<序>；人工投料不会有这个形状
        assert uid.startswith("job_"), uid
        assert jobstore.get_job(uid) is not None, uid
        assert _status(uid) in SETTLED, (_status(uid), uid)
    done_dir = chain["queue"] / "_done"
    assert done_dir.is_dir() and list(done_dir.glob("*.json")), \
        "Planner 落的 spec 应在出片成功后归档进 queue_15s/_done"


# ── ② 终态与设计内 BLOCKED ────────────────────────────────────────────
def test_every_job_reaches_an_expected_state(chain):
    reached = _uids_with(chain, REACHED)
    blocked = _uids_with(chain, {JobState.BLOCKED})
    assert len(reached) + len(blocked) == 5, {u: _status(u) for u in chain["uids"]}
    assert len(reached) >= 4, "本机实测：只有高风险新构图那一条会被设计内拦下"
    for uid in blocked:
        job = jobstore.get_job(uid)
        assert job["error_code"] == PRESCREEN_REQUIRED, (uid, job["error_code"])
        # 被预筛拦下的任务绝不能进过付费阶段
        assert [a["stage"] for a in jobstore.list_attempts(uid)] == ["plan", "preflight"]
        assert float(job["cost_spent"] or 0.0) == 0.0


# ── ③ 无重复提交 / 无残留句柄 ─────────────────────────────────────────
def test_batch_submits_each_paid_task_exactly_once(chain):
    provider = chain["provider"]
    reached = _uids_with(chain, REACHED)
    assert provider.submit_count == len(reached), (
        "每条成片只该提交一次付费任务", provider.submitted)
    assert provider.submit_attempts == provider.submit_count, provider.submit_attempts
    task_ids = [s["task_id"] for s in provider.submitted]
    assert len(set(task_ids)) == len(task_ids), task_ids


def test_batch_leaves_no_orphan_handle_or_uncaught_failure(chain):
    status = chain["orch"].status()
    assert status["running"] is False, status
    assert chain["orch"]._handles == {} and chain["orch"]._pending == 0
    for uid in chain["uids"]:
        codes = [e.get("error_code") for e in jobstore.list_events(uid)
                 if e.get("type") == "stage_failed"]
        assert "UNEXPECTED_ERROR" not in codes, (uid, codes)


# ── ④ 创意产物可查询（Research/DNA/StorySpec/prompt）──────────────────
def test_creative_artifacts_and_compiled_prompt_are_queryable(chain):
    reached = _uids_with(chain, REACHED)
    assert reached, "至少要有一条成片才能验收可查询性"
    for uid in reached:
        kinds = set(_artifacts(uid))
        missing = (set(PLAN_ARTIFACTS) | set(VIDEO_ARTIFACTS)) - kinds
        assert not missing, (uid, sorted(missing), sorted(kinds))
        doc = S.spec_of(jobstore, uid, chain["queue"])
        assert doc.get("prompt_ready") is True, uid
        assert str(doc.get("prompt") or "").strip(), uid
        dna = (doc.get("creative") or {}).get("dna") or {}
        assert dna.get("genre") and dna.get("hook_type") and dna.get("shot_pattern"), (uid, dna)
        story = doc.get("story_spec") or {}
        assert story.get("shots"), (uid, "StorySpec 缺 shots")
        # 研究依据也必须能查到（不是只有一句空壳）
        research = json.loads(Path(_artifacts(uid)["research"]).read_text(encoding="utf-8"))
        assert research, (uid, "research artifact 为空")


# ── ⑤ 三维结构差异 ────────────────────────────────────────────────────
def test_planned_dimensions_are_structurally_varied(chain):
    rows = [m for m in (_plan_metrics(u) for u in chain["uids"]) if m]
    assert len(rows) == 5, rows
    dims = {key: {str(r.get(key) or "") for r in rows} - {""}
            for key in ("genre", "hook_type", "shot_pattern")}
    for key, values in dims.items():
        assert len(values) >= 2, (key, values, f"5 条片在 {key} 上完全没有差异")
    total = sum(len(v) for v in dims.values())
    assert total >= 8, (dims, "三个维度的取值总数太少，等于在重复同一条片")


# ── ⑥ Claims Gate 把注入的虚假参数挡在付费之前 ────────────────────────
def test_claims_gate_blocks_injected_fabrication_before_paid_generation(tmp_state):
    """§15.1-4：往自主规划产出的 spec 里注入没登记的数值承诺 → 必须在付费前拦下。"""
    from lib.creative import planner as planner_mod

    mp = pytest.MonkeyPatch()
    try:
        S.no_real_autodl(mp)
        S.install_lines(mp)
        queue = tmp_state / "queue_15s"
        planned = planner_mod.plan_missing(store=jobstore, daily_target=1, count=1,
                                           queue_dir=queue, state_dir=tmp_state,
                                           goal="Phase15注入")
        assert len(planned) == 1, planned
        pj = planned[0]
        doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
        doc.setdefault("creative", {}).setdefault("dna", {})["payoff"] = "承重 300 公斤"
        Path(pj.spec_path).write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
        jobstore.create_job(goal="Phase15注入", uid=pj.uid)

        provider = S.new_provider()
        orch = S.build_orchestrator(jobstore, tmp_state, provider=provider)
        cfg = RunConfig(goal="Phase15注入", source="test", daily_target=1,
                        max_repairs=0, stages=list(stages_mod.STAGE_ORDER))
        res = orch.start(cfg, background=False)
        assert pj.uid in res["jobs"], res
    finally:
        mp.undo()

    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == CLAIM_UNMAPPED, (job["error_code"], job["error"])
    assert provider.submit_count == 0, "合规门不通过绝不能触发付费提交"
    assert [a["stage"] for a in jobstore.list_attempts(pj.uid)] == ["plan", "preflight"]
    assert float(job["cost_spent"] or 0.0) == 0.0


# ── ⑦ 后期只认一份 canonical transcript ───────────────────────────────
def test_post_stage_keeps_exactly_one_canonical_transcript(chain):
    from lib.post.transcript import Segment

    uid = _uids_with(chain, REACHED)[0]
    workspace = chain["state"] / "out" / f"gen_{uid}"
    video = workspace / "onetake_final.mp4"
    assert video.is_file()

    calls = {"n": 0}

    def fake_asr(_video):
        calls["n"] += 1
        return ([Segment(start=0.0, end=1.5, text="第一句")],
                {"model": "fake-asr", "language": "zh"})

    first, reused = transcript_mod.ensure(video, workspace=workspace, uid=uid,
                                          transcriber=fake_asr)
    assert reused is False and calls["n"] == 1
    second, reused_again = transcript_mod.ensure(video, workspace=workspace, uid=uid,
                                                 transcriber=fake_asr)
    assert reused_again is True and calls["n"] == 1, "第二遍必须命中 canonical，不再跑 ASR"
    assert second.fingerprint() == first.fingerprint()
    canonical = transcript_mod.canonical_path(workspace)
    assert canonical.is_file()
    found = sorted(p for p in workspace.rglob("*.json") if "canonical" in p.name)
    assert found == [canonical], found
    assert transcript_mod.matches_source(first, video), "canonical 必须能对上这条成片"
    assert transcript_mod.load(workspace).fingerprint() == first.fingerprint()


# ── ⑧ packaging 完整（标题/描述/claim ids/AI 声明）────────────────────
def test_every_ready_job_carries_complete_packaging(chain):
    for uid in _uids_with(chain, REACHED):
        brief = json.loads(Path(_artifacts(uid)["packaging"]).read_text(encoding="utf-8"))
        assert str(brief.get("title") or "").strip(), (uid, brief)
        assert str(brief.get("description") or "").strip(), uid
        assert brief.get("title_candidates") and brief.get("hashtags"), uid
        assert "claim_ids" in brief, brief.keys()
        assert brief.get("ai_generated") is True, uid
        assert brief.get("targets"), uid
        for target in brief["targets"]:
            assert target.get("platform"), target
            assert target.get("mode") in ("direct", "draft", "require_human"), target
            assert "requires_ai_disclosure" in target, target
        disclosure = brief.get("disclosure") or {}
        assert disclosure.get("mode"), disclosure


# ── ⑨ WebUI 与 JobStore 是同一份事实 ─────────────────────────────────
def test_webui_reports_the_same_truth_as_jobstore(chain, monkeypatch):
    from fastapi.testclient import TestClient

    from webui import server

    monkeypatch.setattr(server, "CONSOLE_STATE_FILE",
                        chain["state"] / "console.json", raising=False)
    monkeypatch.setattr(server, "STATE_DIR", chain["state"], raising=False)
    client = TestClient(server.app)

    state_view = client.get("/api/state").json()
    assert state_view["run"]["source_of_truth"] == "jobstore", state_view

    for uid in chain["uids"]:
        job = jobstore.get_job(uid)
        view = client.get(f"/api/job/{uid}").json()
        assert view["job"]["status"] == job["status"], uid
        assert view["summary"]["status"] == job["status"], uid
        assert str(view["summary"]["cost_spent"]) == str(job["cost_spent"]), uid
        assert len(view["attempts"]) == len(jobstore.list_attempts(uid)), uid
        assert view["repair_summary"]["count"] == jobstore.repair_summary(uid)["count"], uid
        assert len(view["events"]) == len(jobstore.list_events(uid)), uid
        qa_rows = [e for e in jobstore.list_evaluations(uid)
                   if str(e["kind"]).startswith("qa")]
        assert view["qa"]["count"] == len(qa_rows), (uid, view["qa"]["count"], len(qa_rows))
        if _status(uid) in REACHED:
            assert view["creative"], (uid, "WebUI 读不到 CreativeDNA")
            assert view["blocked"] is None, (uid, view["blocked"])
        else:
            assert (view["blocked"] or {}).get("code") == PRESCREEN_REQUIRED, view["blocked"]
