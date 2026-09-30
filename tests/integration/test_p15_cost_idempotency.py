"""Phase 15.3 —— 成本与幂等（fake provider 的调用账本必须逐项对得上）。

  · create / query / download 三类调用可分别统计；
  · 同一 attempt 重跑不重复 create_task（指纹命中 → 只查询/只复用）；
  · 下载失败只增加 download 次数，绝不重新提交付费任务；
  · 供应商业务拒绝**不是**网络抖动：提交次数有上限、错误码不伪装成 NETWORK_TRANSIENT；
  · 超预算在付费前就 BLOCKED_BUDGET；
  · 每 job 的预估 / 已发生 / 修复成本分别可读；
  · 预筛成本与正式生成成本分开记录（不混进同一条账）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.creative import planner as planner_mod
from lib.creative.prescreen import needs_prescreen
from lib.jobstore import JobState
from lib.jobstore import store as jobstore
from lib.orchestrator import RunConfig
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import BLOCKED_BUDGET, NETWORK_TRANSIENT, PROVIDER_REJECTED
from lib.orchestrator.generation import IdempotentGenerator
from tests import p15_support as S

pytestmark = pytest.mark.integration

GOAL = "Phase15成本幂等"


@pytest.fixture(autouse=True)
def _no_autodl(monkeypatch):
    return S.no_real_autodl(monkeypatch)


@pytest.fixture()
def lines(monkeypatch):
    return S.install_lines(monkeypatch)


def _pick(tmp_state, *, count: int = 4):
    planned = planner_mod.plan_missing(store=jobstore, daily_target=count, count=count,
                                       queue_dir=tmp_state / "queue_15s",
                                       state_dir=tmp_state, goal=GOAL)
    for pj in planned:
        if not needs_prescreen(json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))):
            return pj
    raise AssertionError("没有低风险稿子")


def _generator(tmp_state, provider=None):
    provider = provider if provider is not None else S.new_provider()
    gen = IdempotentGenerator(jobstore, provider, root=tmp_state, log=lambda _m: None,
                              sleep=lambda _s: None, download_retries=3)
    return gen, provider


# ── ① / ② 同一 attempt 重跑不重复 create_task ─────────────────────────
def test_repeat_generation_reuses_the_submitted_task(tmp_state, lines):
    pj = _pick(tmp_state)
    doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    gen, provider = _generator(tmp_state)
    out = tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4"

    first = gen.generate(uid=pj.uid, prompt=doc["prompt"], duration=15,
                         resolution=doc.get("resolution") or "768p竖",
                         workflow=doc["workflow"],
                         fallback_workflows=doc.get("fallback_workflows") or [],
                         ref_images=doc.get("ref_images") or [],
                         ref_audios=doc.get("ref_audios") or [],
                         out_path=out)
    assert first.reused is False
    assert (provider.submit_count, provider.query_calls, provider.download_calls) == (1, 1, 1)

    again = gen.generate(uid=pj.uid, prompt=doc["prompt"], duration=15,
                         resolution=doc.get("resolution") or "768p竖",
                         workflow=doc["workflow"],
                         fallback_workflows=doc.get("fallback_workflows") or [],
                         ref_images=doc.get("ref_images") or [],
                         ref_audios=doc.get("ref_audios") or [],
                         out_path=out)
    assert again.reused is True, "同 uid + 同 prompt + 同工作流必须命中指纹，不再提交"
    assert provider.submit_count == 1, "重跑绝不许重复 create_task"
    assert provider.download_calls == 1, "产物已在本地 → 不该重下"
    events = [e["type"] for e in jobstore.list_events(pj.uid)]
    assert "provider_reused" in events, events
    tasks = jobstore.list_provider_tasks(pj.uid, stage="generate")
    assert len(tasks) == 1 and tasks[0]["task_id"], tasks


# ── ③ 下载失败只增 download，不重提交 ────────────────────────────────
def test_download_failure_only_costs_extra_download_attempts(tmp_state, lines):
    pj = _pick(tmp_state)
    doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    gen, provider = _generator(tmp_state)
    provider.download_fail_times = 1

    out = tmp_state / "out" / f"gen_{pj.uid}" / "onetake.mp4"
    outcome = gen.generate(uid=pj.uid, prompt=doc["prompt"], duration=15,
                           resolution=doc.get("resolution") or "768p竖",
                           workflow=doc["workflow"],
                           fallback_workflows=doc.get("fallback_workflows") or [],
                           ref_images=doc.get("ref_images") or [],
                           ref_audios=doc.get("ref_audios") or [],
                           out_path=out)
    assert out.is_file()
    assert provider.submit_count == 1, "下载失败不许重新提交付费任务"
    assert provider.download_calls == 2, "只该多下一次"
    assert outcome.workflow == doc["workflow"]
    kinds = [e["type"] for e in jobstore.list_events(pj.uid)]
    assert "download_retry" in kinds, kinds


# ── ④ 业务拒绝 ≠ 网络抖动（有上限、不伪装错误码）────────────────────
def test_business_rejection_is_bounded_not_retried_as_network(tmp_state, lines):
    planned = planner_mod.plan_missing(store=jobstore, daily_target=4, count=4,
                                       queue_dir=tmp_state / "queue_15s",
                                       state_dir=tmp_state, goal=GOAL)
    pj = next(p for p in planned
              if json.loads(Path(p.spec_path).read_text(encoding="utf-8")).get("workflow")
              and not needs_prescreen(json.loads(Path(p.spec_path).read_text(encoding="utf-8"))))
    doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
    doc["fallback_workflows"] = []          # 没有可换的链 → 只能撞在同一个拒绝上
    Path(pj.spec_path).write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                  encoding="utf-8")

    provider = S.new_provider()
    provider.fail_workflows = {doc["workflow"]}
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider, docs={pj.uid: doc})
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_attempts=3, max_repairs=0,
                    stages=list(stages_mod.STAGE_ORDER))
    assert orch.start(cfg, specs=[pj.spec_path], background=False)["ok"] is True

    job = jobstore.get_job(pj.uid)
    assert job["status"] in (JobState.BLOCKED, JobState.FAILED), job
    assert provider.submit_attempts <= 3, "业务拒绝的重试次数必须有上限"
    assert provider.submit_count == 0 and provider.download_calls == 0
    events = jobstore.list_events(pj.uid)
    codes = [(e.get("data") or {}).get("error_code") for e in events
             if e["type"] == "provider_rejected"]
    assert PROVIDER_REJECTED in [c for c in codes if c], codes
    assert NETWORK_TRANSIENT not in [c for c in codes if c], "业务拒绝不许伪装成网络抖动"
    assert all(e["type"] != "download_retry" for e in events)


# ── ⑤ 超预算在付费前拦停 ─────────────────────────────────────────────
def test_budget_cap_blocks_before_any_paid_submission(tmp_state, lines):
    pj = _pick(tmp_state)
    provider = S.new_provider()
    jobstore.create_job(goal=GOAL, uid=pj.uid, budget_cap=0.5)
    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, budget_cap=0.5, max_repairs=0,
                    stages=list(stages_mod.STAGE_ORDER))
    assert orch.start(cfg, specs=[pj.spec_path], background=False)["ok"] is True

    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == BLOCKED_BUDGET, (job["error_code"], job["error"])
    assert provider.submit_count == 0 and provider.submit_attempts == 0
    assert float(job["cost_spent"] or 0.0) == 0.0
    assert "generate" not in [a["stage"] for a in jobstore.list_attempts(pj.uid)]


# ── ⑥ 预估 / 已发生 / 修复成本分别可读 ───────────────────────────────
def test_costs_are_reported_separately_for_job_and_repairs(tmp_state, lines, monkeypatch):
    from lib.creative.workflow import route_for_spec

    pj = _pick(tmp_state)
    doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
    jobstore.create_job(goal=GOAL, uid=pj.uid)

    provider = S.new_provider()

    def qa_evidence_for(_uid, n):
        if n == 1:
            return S.evidence(doc, product_deformed=True, deformed_parts=["车架"])
        return S.evidence(doc)

    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider, docs={pj.uid: doc},
                                qa_evidence_for=qa_evidence_for)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_repairs=2,
                    stages=list(stages_mod.STAGE_ORDER))
    assert orch.start(cfg, specs=[pj.spec_path], background=False)["ok"] is True
    assert jobstore.get_job(pj.uid)["status"] == JobState.READY

    job = jobstore.get_job(pj.uid)
    estimate = float(route_for_spec(doc).cost_estimate or 0.0)
    assert estimate > 0, "路由必须给出预估成本"
    assert float(job["cost_spent"]) == pytest.approx(0.9, abs=1e-6)
    assert float(job["cost_spent"]) <= estimate * 3, "实付不该离预估一个数量级"

    summary = jobstore.repair_summary(pj.uid)
    assert summary["count"] == 1, summary
    repairs = jobstore.list_repairs(pj.uid)
    assert float(repairs[0]["cost"] or 0.0) == 0.0, "回退重跑复用了成片，修复成本应为 0"
    assert summary["cost"] == pytest.approx(0.0, abs=1e-6)
    # 生成阶段的 attempt 才是那笔 0.9；修复重跑那条 generate 复用了成片、成本为 0
    by_stage: dict[str, float] = {}
    for a in jobstore.list_attempts(pj.uid):
        by_stage[a["stage"]] = by_stage.get(a["stage"], 0.0) + float(a.get("cost") or 0.0)
    assert by_stage["generate"] == pytest.approx(0.9, abs=1e-6), by_stage
    assert all(v == 0.0 for k, v in by_stage.items() if k != "generate"), by_stage

    # WebUI 展示的就是同一组数
    from fastapi.testclient import TestClient

    from webui import server
    monkeypatch.setattr(server, "CONSOLE_STATE_FILE", tmp_state / "console.json",
                        raising=False)
    monkeypatch.setattr(server, "STATE_DIR", tmp_state, raising=False)
    client = TestClient(server.app)
    view = client.get(f"/api/job/{pj.uid}").json()
    assert str(view["summary"]["cost_spent"]) == str(job["cost_spent"]), view["summary"]
    assert view["repair_summary"]["cost"] == summary["cost"], view["repair_summary"]


# ── ⑦ 预筛成本与正式生成成本分开记录 ─────────────────────────────────
def test_prescreen_outcome_never_mixes_into_generation_cost(tmp_state, lines):
    from lib.creative.prescreen import PRESCREEN_EVAL, record_prescreen

    pj = _pick(tmp_state)
    doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    record_prescreen(jobstore, pj.uid, passed=True, detail={"shot": 1})

    provider = S.new_provider()
    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider, docs={pj.uid: doc})
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_repairs=0,
                    stages=list(stages_mod.STAGE_ORDER))
    assert orch.start(cfg, specs=[pj.spec_path], background=False)["ok"] is True

    job = jobstore.get_job(pj.uid)
    assert float(job["cost_spent"]) == pytest.approx(0.9, abs=1e-6)
    prescreen_rows = jobstore.list_evaluations(pj.uid, PRESCREEN_EVAL)
    assert len(prescreen_rows) == 1 and bool(prescreen_rows[0]["passed"]) is True
    # 预筛只留结论、不占生成账；付费任务只有生成那一条
    assert prescreen_rows[0].get("score") is None, prescreen_rows[0]
    tasks = jobstore.list_provider_tasks(pj.uid)
    assert [t["stage"] for t in tasks] == ["generate"], tasks
    assert float(job["cost_spent"]) == pytest.approx(
        sum(float(a.get("cost") or 0.0) for a in jobstore.list_attempts(pj.uid)), abs=1e-6)
