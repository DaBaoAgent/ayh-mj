"""Phase 15.1 第 5/6 条 —— 预筛只对高风险触发、首选工作流失败能 fallback。

  · 低风险 spec：preflight 直接放行，metrics 记 `prescreen=not_required`，不进预筛；
  · 高风险 spec：preflight 返回 PRESCREEN_REQUIRED → BLOCKED，且 0 付费；
    补上真实预筛结论（`record_prescreen`）后 retry，必须能续跑到成片；
  · 首选工作流被供应商拒绝时，`IdempotentGenerator` 的链式回退必须接管，
    提交次数 2、成功 1，且落盘的 workflow 就是 fallback。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.creative import planner as planner_mod
from lib.creative.prescreen import PRESCREEN_EVAL, needs_prescreen, record_prescreen, risk_of
from lib.jobstore import JobState
from lib.jobstore import store as jobstore
from lib.orchestrator import RunConfig
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import PRESCREEN_REQUIRED
from tests import p15_support as S

pytestmark = pytest.mark.integration

GOAL = "Phase15预筛"


@pytest.fixture(autouse=True)
def _no_autodl(monkeypatch):
    return S.no_real_autodl(monkeypatch)


@pytest.fixture()
def lines(monkeypatch):
    return S.install_lines(monkeypatch)


def _doc(pj) -> dict:
    return json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))


def _write(pj, doc: dict) -> None:
    Path(pj.spec_path).write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                  encoding="utf-8")


def _plan(tmp_state, count: int = 8):
    return planner_mod.plan_missing(store=jobstore, daily_target=count, count=count,
                                    queue_dir=tmp_state / "queue_15s",
                                    state_dir=tmp_state, goal=GOAL)


def _run(tmp_state, specs, *, provider=None, max_repairs=0):
    """只跑指定的 spec（显式投料）：本文件的验收对象是门禁行为，不是自主发现。"""
    provider = provider if provider is not None else S.new_provider()
    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=len(specs),
                    max_repairs=max_repairs, stages=list(stages_mod.STAGE_ORDER))
    res = orch.start(cfg, specs=list(specs), background=False)
    return orch, provider, res


def _preflight_metrics(uid: str) -> dict:
    """preflight 的门禁 metrics：成功看 stage_end，被拦看 stage_failed。"""
    found: dict = {}
    for event in jobstore.list_events(uid):
        if event.get("stage") != "preflight":
            continue
        if event.get("type") not in ("stage_end", "stage_failed"):
            continue
        found = dict((event.get("data") or {}).get("metrics") or {}) or found
    return found


# ── ⑤ 低风险：不该被预筛拦 ────────────────────────────────────────────
def test_low_risk_spec_passes_preflight_without_prescreen(tmp_state, lines):
    planned = _plan(tmp_state)
    low = next((pj for pj in planned if not needs_prescreen(_doc(pj))), None)
    assert low is not None, "这一批里必须有低/中风险的稿子（否则预筛门就是无差别拦截）"
    doc = _doc(low)
    assert risk_of(doc)["level"] in ("low", "medium"), risk_of(doc)

    jobstore.create_job(goal=GOAL, uid=low.uid)
    _orch, provider, res = _run(tmp_state, [low.spec_path])
    assert res["ok"] is True, res

    job = jobstore.get_job(low.uid)
    assert job["status"] == JobState.READY, (job["status"], job["error_code"])
    metrics = _preflight_metrics(low.uid)
    assert metrics["prescreen"] == "not_required", metrics
    assert metrics["risk_level"] in ("low", "medium"), metrics
    assert provider.submit_count == 1, provider.submitted
    # 低风险不需要任何预筛结论
    assert jobstore.list_evaluations(low.uid, PRESCREEN_EVAL) == []


# ── ⑤ 高风险：先拦，补预筛结论后放行 ──────────────────────────────────
def test_high_risk_spec_needs_a_real_prescreen_before_paid_generation(tmp_state, lines):
    planned = _plan(tmp_state)
    pick = planned[0]
    doc = _doc(pick)
    # 把风险顶到 high：危险形变动作 + 身体状态设定（外加本来就有的新骨架 0.2）
    doc["creative"]["dna"].update({"visual_motif": "折叠收放", "conflict_type": "身体不便"})
    _write(pick, doc)
    assert needs_prescreen(_doc(pick)) is True, risk_of(_doc(pick))

    jobstore.create_job(goal=GOAL, uid=pick.uid)
    provider = S.new_provider()
    orch, provider, res = _run(tmp_state, [pick.spec_path], provider=provider)
    assert res["ok"] is True, res

    job = jobstore.get_job(pick.uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == PRESCREEN_REQUIRED, (job["error_code"], job["error"])
    assert provider.submit_count == 0, "预筛未过绝不能进付费生成"
    assert [a["stage"] for a in jobstore.list_attempts(pick.uid)] == ["plan", "preflight"]
    assert float(job["cost_spent"] or 0.0) == 0.0
    assert _preflight_metrics(pick.uid)["prescreen"] == "required"

    # 人工/外部步骤补上预筛结论 → retry 必须能继续走到成片
    record_prescreen(jobstore, pick.uid, passed=True, detail={"shot": 1, "fake": True})
    assert bool(jobstore.list_evaluations(pick.uid, PRESCREEN_EVAL)[0]["passed"]) is True
    resumed = orch.retry(pick.uid, background=False)
    assert resumed["ok"] is True, resumed
    job = jobstore.get_job(pick.uid)
    assert job["status"] == JobState.READY, (job["status"], job["error_code"])
    assert provider.submit_count == 1
    assert _preflight_metrics(pick.uid)["prescreen"] in ("passed", "required")


# ── ⑥ 首选工作流失败 → 自动 fallback ──────────────────────────────────
def test_rejected_preferred_workflow_falls_back_without_double_charging(tmp_state, lines):
    planned = _plan(tmp_state, count=4)
    pick = next(pj for pj in planned
                if not needs_prescreen(_doc(pj))
                and _doc(pj).get("workflow") and (_doc(pj).get("fallback_workflows") or []))
    doc = _doc(pick)
    preferred, fallback = doc["workflow"], doc["fallback_workflows"][0]
    assert preferred != fallback

    provider = S.new_provider()
    provider.fail_workflows = {preferred}
    jobstore.create_job(goal=GOAL, uid=pick.uid)
    _orch, provider, res = _run(tmp_state, [pick.spec_path], provider=provider)
    assert res["ok"] is True, res

    job = jobstore.get_job(pick.uid)
    assert job["status"] == JobState.READY, (job["status"], job["error_code"])
    assert provider.submit_attempts == 2, "首选被拒后必须再提交一次 fallback"
    assert provider.submit_count == 1, provider.submitted
    assert provider.submitted[0]["workflow"] == fallback, provider.submitted
    task = json.loads((tmp_state / "out" / f"gen_{pick.uid}" / "onetake_task.json")
                      .read_text(encoding="utf-8"))
    assert task["workflow"] == fallback, task
    assert float(job["cost_spent"]) == pytest.approx(0.9, abs=1e-6)
