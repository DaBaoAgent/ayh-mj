"""Phase 5 端到端 —— 空队列自主规划 → CreativeDNA → 付费前收口。

Phase 7 起，规划阶段会**顺带编译 H3 提示词并路由工作流**，所以 Phase 5 时代
"`plan_only=True` 停在 `PROMPT_NOT_COMPILED`"的边界不再适用于自己规划出来的 spec：
它已经带 prompt（`prompt_ready=True`），拦住付费的是**预筛门**（高风险新构图）或
**台词缺失**。`PROMPT_NOT_COMPILED` 仍然是"没编译的 spec 不许付费"的那道闸，
见 `test_uncompiled_spec_is_blocked_before_paid_generation`。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import MISSING_INPUT, PLAN_FAILED, PRESCREEN_REQUIRED, PROMPT_NOT_COMPILED
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
    metrics = plan_end[-1]["data"]["metrics"]
    # Phase 7：规划阶段就编译好了 prompt（plan_only=False）并选好了工作流链
    assert metrics["prompt_ready"] is True and metrics["plan_only"] is False
    assert metrics["prompt_chars"] > 1000
    assert metrics["workflow"] and metrics["workflow_source"] == "router"
    assert metrics["shot_count"] >= 3
    assert metrics["hook_type"] == dna["hook_type"]

    # 规划阶段一分钱都没花
    assert provider.submit_count == 0
    assert float(store.get_job(uid)["cost_spent"] or 0) == 0.0


def test_high_risk_spec_stops_at_prescreen_before_paid_generation(tmp_state, monkeypatch):
    """Phase 7 边界：高风险 spec 必须先过预筛；测试显式固定风险，不依赖 Planner 恰好选中哪条。"""
    monkeypatch.setattr("lib.creative.prescreen.needs_prescreen", lambda _doc: True)
    monkeypatch.setattr("lib.creative.prescreen.risk_of", lambda _doc: {
        "level": "high", "score": 0.9, "reasons": [{"label": "fixture", "weight": 0.9}]})
    provider = FakeProvider()
    orch = _orch(tmp_state, provider,
                 _stages(plan=stages_mod.stage_plan, preflight=stages_mod.stage_preflight))
    uid = orch.start(_cfg(), background=False)["jobs"][0]

    job = store.get_job(uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] in (PRESCREEN_REQUIRED, MISSING_INPUT), job
    assert provider.submit_count == 0, "没过预筛的 StorySpec 绝不能触发付费提交"
    stages_run = [a["stage"] for a in store.list_attempts(uid)]
    assert stages_run == ["plan", "preflight"], stages_run
    assert not (tmp_state / "out" / f"gen_{uid}").exists()


def test_uncompiled_spec_is_blocked_before_paid_generation(tmp_state):
    """Phase 5 的闸门仍然有效：没有 prompt 的 spec（plan_only）一步都不许往前走。"""
    queue = tmp_state / "queue_15s"
    queue.mkdir(parents=True, exist_ok=True)
    path = queue / "UNCOMPILED1.json"
    path.write_text(json.dumps({
        "job_uid": "UNCOMPILED1", "title": "没编译的 spec", "plan_only": True,
        "prompt_ready": False, "prompt": "", "duration": 15,
        "creative": {"dna": {"dialogue_mode": "双人对白", "hook_type": "冲突质问"}},
        "story_spec": {"prompt": "", "shots": [], "lines": []},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    provider = FakeProvider()
    orch = _orch(tmp_state, provider,
                 _stages(plan=stages_mod.stage_plan, preflight=stages_mod.stage_preflight))
    orch.start(_cfg(), specs=[path], background=False)

    job = store.get_job("UNCOMPILED1")
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == PROMPT_NOT_COMPILED
    assert provider.submit_count == 0, "未编译 prompt 的 StorySpec 绝不能触发付费提交"
    assert [a["stage"] for a in store.list_attempts("UNCOMPILED1")] == ["plan", "preflight"]


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
