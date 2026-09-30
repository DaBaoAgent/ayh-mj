"""Phase 13 集成 —— fake LLM + fake generator + fixture 成片跑完整主链到 READY。

计划 §Phase 13 Integration："使用 fake LLM + fake generator + fixture video 跑
Planner → Script → Generate → QA → Repair → Compose → Packaging → READY"。

与既有集成测试的区别：`test_post_pipeline` 只跑后期，`test_qa_repair_pipeline` 用
假 stage 换掉了全部阶段，**没有一条**真的按 `STAGE_ORDER` 从 plan 一路走到 READY
并中途经历一次真实修复回退。这条用例补的就是它。

设计要点：
  · plan / preflight / generate / qa / package 用**真实阶段实现**；
  · 只有 compose 用 fixture 实现（真实 compose 要跑 ffmpeg 子进程，不满足"无网络
    无外部依赖"），但它的最终验片仍然调用产线的真实 QA 门（`_qa_gate(phase="final")`）；
  · 首次 gen 验片用坏证据触发 PRODUCT_DEFORMED，修复环回退 generate 后第二次通过；
  · 全程 0 付费、0 联网：FakeEnv 换掉 LLM 与生成供应商，并把真实 AutoDL 提交
    打上"必炸"桩（本题一旦真的提交就 AssertionError）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.creative import compiler as C
from lib.creative.prescreen import needs_prescreen, record_prescreen, risk_of
from lib.creative.structures import STORY_STRUCTURES
from lib.creative.workflow import route_for_spec
from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import PRODUCT_DEFORMED
from tests.p7_support import spec_for

pytestmark = pytest.mark.integration

STRUCTURE_ID = "S_duo_conflict"
UID = "P13_E2E"
# 真实 delivery 检查要求成片 >= 100000 字节，fixture 成片必须真的大于这个数
VIDEO_BYTES = b"fixture-mp4-payload" * 6000


@pytest.fixture(autouse=True)
def _no_real_autodl(monkeypatch):
    """Phase 15 硬约束：自动测试里任何真实的 AutoDL 提交都必须炸出来。"""
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


# ── 造一份"规划期已编译 + 已路由"的 StorySpec（Planner 落盘同口径） ──────

def _write_compiled_spec(tmp_state) -> tuple[Path, dict]:
    structure = next(s for s in STORY_STRUCTURES if s["id"] == STRUCTURE_ID)
    doc = spec_for(structure, uid=UID, duration=15, claim_ids=["anti_flip"])
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
    path = tmp_state / "queue_15s" / f"{UID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, doc


def _evidence(doc: dict, *, products_seen: int) -> dict:
    """按 spec 现造 QA 证据（台词/时长/说话人全部与 spec 对齐）。"""
    story = doc["story_spec"]
    dna = story["dna"]
    texts = [str(line["text"]) for line in story["lines"] if str(line.get("text", "")).strip()]
    spoken = " ".join(texts)
    duration = float(story["duration"])
    n = max(1, len(texts))
    cues = [{"start": round(duration * i / n, 2), "end": round(duration * (i + 1) / n, 2),
             "text": text} for i, text in enumerate(texts)]
    people = len([s for s in str(dna.get("cast_pattern") or "").split("+") if s.strip()]) or 1
    return {
        "video": {"exists": True, "bytes": len(VIDEO_BYTES), "video_streams": 1,
                  "audio_streams": 1, "duration": duration,
                  "loudness_lufs": -14.0, "true_peak_db": -1.5},
        "vision": {"products_seen": products_seen, "product_deformed": False,
                   "anatomy_ok": True, "wrong_speaker_shots": [], "people_seen": people,
                   "first_hook_seconds": 1.0, "static_seconds": 0.5,
                   "payoff_seconds": 12.0, "non_speaker_mouth_open": False},
        "spec": {"duration": duration, "products_expected": 1, "people_expected": people,
                 "dialogue_mode": dna.get("dialogue_mode") or "",
                 "expected_lines": [{"shot": line.get("shot"), "text": line.get("text")}
                                    for line in story["lines"]]},
        "copy": {"spoken": spoken, "title": str(doc.get("title") or ""),
                 "on_screen": "", "description": ""},
        "subtitle": {"cues": cues},
        "transcript": {"text": spoken},
    }


# ── 阶段实现 ───────────────────────────────────────────────────────────

def _generate_stage():
    """真实 generate 阶段 + fixture 成片（FakeProvider 负责"下载"落地）。"""
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        res = stages_mod.stage_generate(ctx)
        if res.success and not ctx.dry:
            # 把 fake provider 落地的"成片"补到 fixture 尺寸，让 delivery 检查
            # 面对的是真实文件大小，而不是一句声明
            out = ctx.workspace / "onetake.mp4"
            if out.is_file() and out.stat().st_size < len(VIDEO_BYTES):
                out.write_bytes(VIDEO_BYTES)
        return res

    fn.calls = calls
    return fn


def _qa_stage(doc):
    """真实 qa 阶段；第一次喂坏证据（产品数漂移），之后喂好证据。"""
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        payload = _evidence(doc, products_seen=2 if calls["n"] == 1 else 1)
        (ctx.workspace / f"qa_evidence_{ctx.uid}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return stages_mod.stage_qa(ctx)

    fn.calls = calls
    return fn


def _compose_stage(doc):
    """fixture 后期：落地 final + final 证据，验片仍走产线真实门禁。"""
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        src = ctx.workspace / "onetake.mp4"
        final = ctx.workspace / "onetake_final.mp4"
        final.write_bytes(src.read_bytes() if src.is_file() else VIDEO_BYTES)
        (ctx.workspace / f"qa_final_evidence_{ctx.uid}.json").write_text(
            json.dumps(_evidence(doc, products_seen=1), ensure_ascii=False), encoding="utf-8")
        gate = stages_mod._qa_gate(ctx, phase="final", stage="compose")
        artifacts = [{"type": "final", "path": final}, *gate.artifacts]
        if not gate.success:
            return StageResult.fail("compose", gate.error_code or "QA_FAILED", gate.message,
                                    metrics=dict(gate.metrics), artifacts=artifacts,
                                    data=dict(gate.data))
        return StageResult.ok("compose", artifacts=artifacts,
                              metrics={"bytes": final.stat().st_size, **gate.metrics},
                              message="fixture 后期合成完成")

    fn.calls = calls
    return fn


def _artifacts(uid) -> dict:
    return {a["type"]: a["path"] for a in store.list_artifacts(uid)}


# ── 验收：跑完整主链到 READY，中途经历一次真实修复回退 ────────────────

def test_fake_main_chain_reaches_ready_through_a_repair(tmp_state, fake_providers):
    path, doc = _write_compiled_spec(tmp_state)
    env = fake_providers

    store.create_job(goal="Phase13 主链", uid=UID)
    if needs_prescreen(doc):
        record_prescreen(store, UID, passed=True, detail={"shot": 1})

    generate = _generate_stage()
    qa = _qa_stage(doc)
    compose = _compose_stage(doc)
    orch = PipelineOrchestrator(
        store=store,
        stages={"plan": stages_mod.stage_plan, "preflight": stages_mod.stage_preflight,
                "generate": generate, "qa": qa, "compose": compose,
                "package": stages_mod.stage_package},
        queue_dir=tmp_state / "queue_15s", root=tmp_state, sleep=lambda _s: None)

    cfg = RunConfig(goal="Phase13 fake 主链", source="test", daily_target=1,
                    max_repairs=1, stages=list(stages_mod.STAGE_ORDER))
    result = orch.start(cfg, specs=[path], background=False)
    assert result["ok"] is True, result
    assert result["jobs"] == [UID], result

    # ① 终态 READY，且每个阶段都真的跑过
    job = store.get_job(UID)
    assert job["status"] == JobState.READY, job
    stages_run = [a["stage"] for a in store.list_attempts(UID)]
    for stage in ("plan", "preflight", "generate", "qa", "compose", "package"):
        assert stage in stages_run, (stage, stages_run)

    # ② 中途真的发生了一次定点修复：产品漂移 → 回退 generate
    repairs = store.list_repairs(UID)
    assert len(repairs) == 1, repairs
    assert repairs[0]["action"] == "REGENERATE_SHOT"
    assert repairs[0]["rewind_to"] == "generate"
    assert repairs[0]["error_code"] == PRODUCT_DEFORMED
    assert store.repair_summary(UID)["by_code"] == {PRODUCT_DEFORMED: 1}
    assert qa.calls["n"] == 2 and generate.calls["n"] == 2
    assert compose.calls["n"] == 1, "修复不该重跑后期"

    # ③ 无重复 provider submit（第二次 generate 复用已落地的 fixture 成片）
    assert env.log.create_task == 1, "一次生成只该提交一次付费任务，修复不得重复提交"
    assert len(env.log.submitted_tasks) == 1

    # ④ 产物齐备：spec / 成片 / 验片报告 / final / 发布物料
    arts = _artifacts(UID)
    for kind in ("spec", "video", "qa_report", "final", "packaging"):
        assert kind in arts, (kind, sorted(arts))
    # plan 阶段必须把 CreativeDNA 的关键维度带进事件（Planner → Script 可追溯）
    plan_end = [e for e in store.list_events(UID)
                if e["type"] == "stage_end" and e["stage"] == "plan"]
    plan_metrics = plan_end[-1]["data"]["metrics"]
    assert plan_metrics["genre"] and plan_metrics["hook_type"] and plan_metrics["shot_pattern"]
    assert plan_metrics["shot_count"] == len(doc["story_spec"]["shots"])
    brief = json.loads(Path(arts["packaging"]).read_text(encoding="utf-8"))
    assert brief["uid"] == UID
    assert brief["targets"], "packaging 必须给出发布目标"

    # ⑤ 两次验片结论都落库（第一次 fail、修复后第二次 pass），成本为 0
    gen_reports = [bool(e["passed"]) for e in store.list_evaluations(UID, kind="qa_report_gen")]
    assert gen_reports == [False, True], gen_reports
    final_reports = [bool(e["passed"]) for e in store.list_evaluations(UID, kind="qa_report_final")]
    assert final_reports == [True], final_reports

    # ⑥ 成本只记一次生成（768p × 15s = 0.06 × 15 = 0.9）：修复回退不重复计费
    assert float(job["cost_spent"]) == pytest.approx(0.9, abs=1e-6)

    # ⑦ 事件轨迹可完整追踪 stage/修复
    events = store.list_events(UID)
    kinds = {e["type"] for e in events}
    assert {"stage_start", "stage_end", "stage_failed", "repair", "repair_done"} <= kinds
    assert any(e["type"] == "stage_end" and e["stage"] == "package" for e in events)


def test_main_chain_leaves_no_orphan_state_and_is_idempotent(tmp_state, fake_providers):
    """再跑一次同一个 spec：不重复生产、不重复提交，状态保持 READY。"""
    path, doc = _write_compiled_spec(tmp_state)
    store.create_job(goal="Phase13 幂等", uid=UID)
    if needs_prescreen(doc):
        record_prescreen(store, UID, passed=True, detail={"shot": 1})

    generate = _generate_stage()
    stages = {"plan": stages_mod.stage_plan, "preflight": stages_mod.stage_preflight,
              "generate": generate, "qa": _qa_stage(doc), "compose": _compose_stage(doc),
              "package": stages_mod.stage_package}
    orch = PipelineOrchestrator(store=store, stages=stages, queue_dir=tmp_state / "queue_15s",
                                root=tmp_state, sleep=lambda _s: None)
    cfg = RunConfig(goal="Phase13 幂等", source="test", max_repairs=1,
                    stages=list(stages_mod.STAGE_ORDER))

    assert orch.start(cfg, specs=[path], background=False)["ok"]
    assert store.get_job(UID)["status"] == JobState.READY
    first_generate_calls = generate.calls["n"]

    again = orch.start(cfg, specs=[path], background=False)
    assert again["jobs"] == [], "已完成的任务不该重复生产"
    assert UID in (again.get("skipped") or []), again
    assert generate.calls["n"] == first_generate_calls
    assert store.get_job(UID)["status"] == JobState.READY
