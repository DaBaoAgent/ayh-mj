"""Phase 5 端到端 —— 空队列自主规划 → CreativeDNA → 付费前收口。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import PLAN_FAILED, PROMPT_NOT_COMPILED
from lib.orchestrator.models import STAGE_ORDER
from tests.fakes.providers import FakeProvider

pytestmark = pytest.mark.integration


def _fake(name):
    def fn(ctx):
        return StageResult.ok(name, metrics={})
    return fn


def _stages(**overrides):
    stages = {name: _fake(name) for name in STAGE_ORDER}
    stages.update(overrides)
    return stages


def _orch(tmp_state, provider, stages) -> PipelineOrchestrator:
    return PipelineOrchestrator(store=store, stages=stages, provider=provider,
                                queue_dir=tmp_state / "queue_15s", root=tmp_state)


def _cfg(**kw) -> RunConfig:
    kw.setdefault("source", "test")
    kw.setdefault("daily_target", 1)
    return RunConfig(**kw)


def test_autonomous_start_produces_job_and_creative_dna(tmp_state):
    """验收①：空队列点 Start → 自动产生 job + CreativeDNA，且全部可追溯。"""
    provider = FakeProvider()
    orch = _orch(tmp_state, provider, _stages(plan=stages_mod.stage_plan))
    result = orch.start(_cfg(), background=False)
    assert result["ok"] and result["count"] == 1, result

    uid = result["jobs"][0]
    arts = {a["type"]: a["path"] for a in store.list_artifacts(uid)}
    assert {"spec", "research", "creative_dna", "creative_scores"} <= set(arts)
    dna = json.loads(Path(arts["creative_dna"]).read_text(encoding="utf-8"))["dna"]
    assert {"genre", "hook_type", "shot_pattern", "audience", "sales_point"} <= set(dna)

    events = store.list_events(uid)
    plan_end = [e for e in events if e["type"] == "stage_end" and e["stage"] == "plan"]
    assert plan_end and plan_end[-1]["data"]["metrics"]["plan_only"] is True
    assert plan_end[-1]["data"]["metrics"]["hook_type"] == dna["hook_type"]

    # 规划阶段一分钱都没花
    assert provider.submit_count == 0
    assert float(store.get_job(uid)["cost_spent"] or 0) == 0.0


def test_plan_only_spec_is_blocked_before_paid_generation(tmp_state):
    """Phase 5 边界：StorySpec 就绪但 H3 prompt 未编译 → 停在 BLOCKED，绝不进付费生成。"""
    provider = FakeProvider()
    orch = _orch(tmp_state, provider,
                 _stages(plan=stages_mod.stage_plan, preflight=stages_mod.stage_preflight))
    uid = orch.start(_cfg(), background=False)["jobs"][0]

    job = store.get_job(uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == PROMPT_NOT_COMPILED
    assert provider.submit_count == 0, "未编译 prompt 的 StorySpec 绝不能触发付费提交"
    stages_run = [a["stage"] for a in store.list_attempts(uid)]
    assert stages_run == ["plan", "preflight"], stages_run
    assert not (tmp_state / "out" / f"gen_{uid}").exists()


def test_planner_failure_creates_no_job_and_no_submission(tmp_state, monkeypatch):
    """验收③：规划失败 → 一个 job 都不建，更不会进入付费 GENERATING。"""

    def boom(*_a, **_k):
        raise RuntimeError("创作知识库不完整：热点库")

    monkeypatch.setattr("lib.creative.planner.build_research_brief", boom)
    provider = FakeProvider()
    orch = _orch(tmp_state, provider, _stages(plan=stages_mod.stage_plan))
    result = orch.start(_cfg(), background=False)

    assert result["ok"] is False and result["error_code"] == "PLAN_FAILED", result
    assert result["jobs"] == []
    assert store.counts()["total"] == 0
    assert provider.submit_count == 0


def test_plan_stage_failure_stops_before_generation(tmp_state, monkeypatch):
    """阶段级：plan 失败 → 下游不跑，job BLOCKED，提交数为 0。"""
    monkeypatch.setattr("lib.creative.planner.build_research_brief",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("热点库空")))
    provider = FakeProvider()
    orch = _orch(tmp_state, provider, _stages(plan=stages_mod.stage_plan))
    cfg = _cfg()
    uid = store.create_job(goal="规划失败", uid="PLANFAIL1",
                           config_snapshot=cfg.to_dict())
    orch._execute(uid, cfg)

    job = store.get_job(uid)
    assert job["status"] == JobState.BLOCKED
    assert job["error_code"] == PLAN_FAILED
    assert [a["stage"] for a in store.list_attempts(uid)] == ["plan"]
    assert provider.submit_count == 0
