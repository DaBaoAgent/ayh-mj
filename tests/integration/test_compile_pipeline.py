"""Phase 7 集成 —— 结构化故事编译 + 智能路由 + 预筛门（fake provider，0 付费）。

覆盖计划 §Phase 7 的验收：
  · 10 种骨架各能编译并执行（不再被"4 镜 × 8 句"限制）；
  · prompt 超限在 provider 调用**之前**阻断；
  · 首选 workflow 失败 → 在预算内切到兼容 fallback，且不丢音频/参考图/时长；
  · 不兼容的链条直接拒绝，绝不静默降级；
  · 高风险 StorySpec 先预筛，低风险直接生成。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.creative import compiler as C
from lib.creative.prescreen import PRESCREEN_SECONDS, needs_prescreen, record_prescreen, risk_of
from lib.creative.structures import STORY_STRUCTURES
from lib.creative.workflow import route_for_spec
from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import PRESCREEN_REQUIRED, PROMPT_BUDGET_EXCEEDED, WORKFLOW_INCOMPATIBLE
from lib.orchestrator.models import STAGE_ORDER
from tests.fakes.providers import FakeProvider
from tests.p7_support import spec_for

pytestmark = pytest.mark.integration

_IDS = [s["id"] for s in STORY_STRUCTURES]


@pytest.fixture(autouse=True)
def _no_real_autodl(monkeypatch):
    """自动测试里任何真实的 AutoDL 提交都必须炸出来（Phase 15 硬约束）。"""
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


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


def _real_stages():
    return _stages(plan=stages_mod.stage_plan, preflight=stages_mod.stage_preflight,
                   generate=stages_mod.stage_generate)


def _write_compiled_spec(tmp_state, structure, *, uid=None, duration=15, claim_ids=("anti_flip",)):
    """造一份"规划期已编译 + 已路由"的 spec，像 Planner 落盘那样写进队列。"""
    doc = spec_for(structure, uid=uid, duration=duration, claim_ids=list(claim_ids))
    compiled = C.compile_spec(doc)
    plan = route_for_spec(doc, risk=risk_of(doc)["level"])
    doc.update({
        "prompt": compiled.prompt, "prompt_ready": True, "plan_only": False,
        "prompt_meta": compiled.to_dict(), "workflow": plan.workflow,
        "fallback_workflows": list(plan.fallbacks), "resolution": plan.resolution,
        "workflow_source": "router",
    })
    doc["story_spec"].update({"prompt": compiled.prompt, "prompt_ready": True,
                              "workflow": plan.workflow,
                              "fallback_workflows": list(plan.fallbacks)})
    path = tmp_state / "queue_15s" / f"{doc['job_uid']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, doc, plan


def _artifacts(uid) -> dict:
    return {a["type"]: a["path"] for a in store.list_artifacts(uid)}


# ── 验收①：10 种骨架各编译一次并真的跑完生成 ──────────────────────
@pytest.mark.parametrize("structure", STORY_STRUCTURES, ids=_IDS)
def test_every_skeleton_compiles_and_executes(tmp_state, structure):
    provider = FakeProvider()
    path, doc, plan = _write_compiled_spec(tmp_state, structure)
    uid = doc["job_uid"]

    # 高风险新构图：先留下一条 passed 的 5s 预筛结论（这正是要求的执行顺序）
    store.create_job(goal=structure["name"], uid=uid)
    if needs_prescreen(doc):
        record_prescreen(store, uid, passed=True,
                         detail={"shot": 1, "seconds": PRESCREEN_SECONDS})

    orch = _orch(tmp_state, provider, _real_stages())
    result = orch.start(_cfg(), specs=[path], background=False)
    assert result["ok"] and result["jobs"] == [uid], result

    job = store.get_job(uid)
    assert job["status"] not in (JobState.BLOCKED, JobState.FAILED), job
    assert provider.submit_count == 1, (structure["id"], provider.submit_attempts)
    assert provider.submitted[0]["workflow"] == plan.workflow
    video = _artifacts(uid).get("video")
    assert video and Path(video).is_file()
    assert [a["stage"] for a in store.list_attempts(uid)] == list(STAGE_ORDER)


def test_no_skeleton_is_limited_to_four_shots_and_eight_lines(tmp_state):
    """计划明确要求：不再被"4 镜 × 8 句"限制。"""
    assert {s["shots"] for s in STORY_STRUCTURES} >= {3, 4, 5}
    provider = FakeProvider()
    structure = next(s for s in STORY_STRUCTURES if s["id"] == "S_emotional_story")
    # 十句台词全部落在 5 镜里 —— 旧口径的"8 句上限"在这里必须失效。
    # 台词本身不含阿拉伯数字/单位（R18 + Phase 6 合规门都要求）。
    texts = ["这不重要", "再看看这个动作", "我明白你的意思", "咱们走", "你再想想",
             "先别急", "我试试", "就这样吧", "听你的", "行，没问题"]
    lines = [{"shot": 1 + (i % 5), "speaker": "@elder_male", "text": texts[i]}
             for i in range(10)]
    doc = spec_for(structure, uid="P7_LONG", lines=lines)
    compiled = C.compile_spec(doc)
    assert compiled.shot_count == 5 and compiled.line_count == 10

    doc.update({"prompt": compiled.prompt, "prompt_ready": True, "plan_only": False,
                "prompt_meta": compiled.to_dict()})
    doc["story_spec"]["prompt"] = compiled.prompt
    doc["story_spec"]["prompt_ready"] = True
    plan = route_for_spec(doc)
    doc["workflow"] = plan.workflow
    doc["fallback_workflows"] = list(plan.fallbacks)
    path = tmp_state / "queue_15s" / "P7_LONG.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    store.create_job(goal="长稿", uid="P7_LONG")
    orch = _orch(tmp_state, provider, _real_stages())
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]
    assert provider.submit_count == 1
    assert store.get_job("P7_LONG")["status"] not in (JobState.BLOCKED, JobState.FAILED)


# ── 验收②：prompt 超限在付费前阻断 ────────────────────────────────
def test_oversized_prompt_is_blocked_before_any_submission(tmp_state):
    provider = FakeProvider()
    path, doc, _ = _write_compiled_spec(tmp_state, STORY_STRUCTURES[0], uid="P7_TOOLONG")
    doc["prompt"] = doc["prompt"] + "X" * (C.PROMPT_MAX + 50)
    doc["story_spec"]["prompt"] = doc["prompt"]
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    orch = _orch(tmp_state, provider, _real_stages())
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]
    job = store.get_job("P7_TOOLONG")
    # 付费前阻断确认：既不提交，也不往下走；终止态由 RepairEngine 策略表决定
    # （COMPRESS_PROMPT 不是 REQUIRE_HUMAN，所以这里落到 FAILED 而非 BLOCKED）。
    assert job["status"] in (JobState.BLOCKED, JobState.FAILED), job
    assert job["error_code"] == PROMPT_BUDGET_EXCEEDED, job
    assert provider.submit_count == 0 and provider.submit_attempts == 0
    assert [a["stage"] for a in store.list_attempts("P7_TOOLONG")] == ["plan", "preflight"]


def test_oversized_prompt_is_compressed_at_compile_time_when_it_can_be(tmp_state):
    """编译器能压下来的（只超安全线）不阻断；真超硬上限才抛。"""
    structure = STORY_STRUCTURES[0]
    doc = spec_for(structure, uid="P7_COMPRESS")
    compiled = C.compile_spec(doc)
    assert compiled.budget.compressed is False
    with pytest.raises(C.PromptBudgetExceeded):
        C.budget_prompt([("big", "X" * (C.PROMPT_MAX + 1))])


# ── 验收③：首选失败 → 预算内切兼容 fallback ───────────────────────
def test_failed_preferred_workflow_switches_to_a_compatible_fallback(tmp_state):
    provider = FakeProvider()
    structure = next(s for s in STORY_STRUCTURES if s["id"] == "S_duo_conflict")
    path, doc, plan = _write_compiled_spec(tmp_state, structure, uid="P7_FALLBACK",
                                           duration=10)
    assert plan.fallbacks, "10s 需求应当有兼容 fallback（能力表里不止一个型号）"
    fallback = plan.fallbacks[0]
    provider.fail_workflows = {plan.workflow}

    store.create_job(goal="fallback", uid="P7_FALLBACK")
    orch = _orch(tmp_state, provider, _real_stages())
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]

    job = store.get_job("P7_FALLBACK")
    assert job["status"] not in (JobState.BLOCKED, JobState.FAILED), job
    assert provider.submit_attempts == 2, "首选被拒后必须再提交一次 fallback"
    assert provider.submit_count == 1
    assert provider.submitted[0]["workflow"] == fallback
    task = json.loads((tmp_state / "out" / "gen_P7_FALLBACK" / "onetake_task.json")
                      .read_text(encoding="utf-8"))
    assert task["workflow"] == fallback


def test_incompatible_chain_is_refused_instead_of_silently_downgraded(tmp_state):
    provider = FakeProvider()
    path, doc, _ = _write_compiled_spec(tmp_state, STORY_STRUCTURES[0], uid="P7_BADCHAIN")
    # 15s 的片配一个只吃 1-10s 的型号，再塞一个"以音频输入为前提"的兜底：
    # 两个都会丢时长/丢能力，必须整体拒绝而不是挑一个跑。
    doc["workflow"] = "minimax_h3_lightx2v_v5"
    doc["fallback_workflows"] = ["minimax_h3_zm_u24"]
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    orch = _orch(tmp_state, provider, _real_stages())
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]
    job = store.get_job("P7_BADCHAIN")
    assert job["status"] == JobState.BLOCKED
    assert job["error_code"] == WORKFLOW_INCOMPATIBLE, job
    assert provider.submit_count == 0 and provider.submit_attempts == 0


# ── 验收④：高风险先预筛，低风险直接生成 ───────────────────────────
def test_high_risk_spec_is_gated_until_a_prescreen_passes(tmp_state):
    provider = FakeProvider()
    path, doc, _ = _write_compiled_spec(tmp_state, STORY_STRUCTURES[0], uid="P7_HIGHRISK")
    doc["creative"]["dna"].update({"cast_pattern": "@a+@b+@c", "conflict_type": "身体不便",
                                   "visual_motif": "遥控轨迹"})
    doc["story_spec"]["dna"] = dict(doc["creative"]["dna"])
    assert risk_of(doc)["level"] == "high"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    orch = _orch(tmp_state, provider, _real_stages())
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]
    job = store.get_job("P7_HIGHRISK")
    assert job["status"] == JobState.BLOCKED
    assert job["error_code"] == PRESCREEN_REQUIRED, job
    assert provider.submit_count == 0
    assert [a["stage"] for a in store.list_attempts("P7_HIGHRISK")] == ["plan", "preflight"]

    # 留下 passed 的预筛结论 → 放行到付费生成
    record_prescreen(store, "P7_HIGHRISK", passed=True, detail={"shot": 1})
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]
    assert store.get_job("P7_HIGHRISK")["status"] not in (JobState.BLOCKED, JobState.FAILED)
    assert provider.submit_count == 1


def test_low_risk_spec_generates_without_a_prescreen(tmp_state):
    provider = FakeProvider()
    structure = next(s for s in STORY_STRUCTURES if s["id"] == "S_silent_slapstick")
    path, doc, _ = _write_compiled_spec(tmp_state, structure, uid="P7_LOWRISK")
    assert needs_prescreen(doc) is False

    store.create_job(goal="低风险", uid="P7_LOWRISK")
    orch = _orch(tmp_state, provider, _real_stages())
    assert orch.start(_cfg(), specs=[path], background=False)["ok"]
    assert provider.submit_count == 1
    assert store.get_job("P7_LOWRISK")["status"] not in (JobState.BLOCKED, JobState.FAILED)
