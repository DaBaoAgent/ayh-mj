"""Phase 8 集成 —— QA Critic → RepairEngine → 定点回退 的完整闭环（fake provider，0 付费）。

覆盖计划 §Phase 8 验收：
  · QA FAIL 必须带 error_code，并落 qa_report artifact + evaluation；
  · 画面不合格 → 回退 generate 重生，次数到上限即转人工 BLOCKED（绝不死循环）；
  · 字幕/ASR 类 → 只回退 compose 重建字幕，**不重生视频**；
  · 合规类 → 直接交人工，不许绕过去重生；
  · 每次修复的次数/成本/结果都能从 DB 审计到。
"""
from __future__ import annotations

import json

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import (
    COMPLIANCE_BLOCK,
    PRODUCT_DEFORMED,
    SUBTITLE_ALIGN_FAIL,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _no_real_autodl(monkeypatch):
    """自动测试里任何真实的 AutoDL 提交都必须炸出来（Phase 15 硬约束）。"""
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


GOOD_VIDEO = {"exists": True, "bytes": 150_000, "video_streams": 1,
              "audio_streams": 1, "duration": 15.0}


def _write_spec(state, uid: str) -> object:
    path = state / f"{uid}.json"
    path.write_text(json.dumps({"job_uid": uid, "title": "", "duration": 15,
                                "prompt": "16 秒 one-take 演示 spec"}, ensure_ascii=False),
                    encoding="utf-8")
    return path


def _write_evidence(workspace, uid: str, payload: dict) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / f"qa_evidence_{uid}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _generate(state, uid: str):
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        out = ctx.workspace / "onetake.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 150_000)
        return StageResult.ok("generate", artifacts=[{"type": "video", "path": out}],
                              metrics={"cost": 0.0})

    fn.calls = calls
    return fn


def _compose(state, uid: str):
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        final = ctx.workspace / "onetake_final.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"y" * 150_000)
        return StageResult.ok("compose", artifacts=[{"type": "final", "path": final}],
                              metrics={})

    fn.calls = calls
    return fn


def _orch(state, stages) -> PipelineOrchestrator:
    return PipelineOrchestrator(store=store, stages=stages, queue_dir=state / "queue_15s",
                                root=state, sleep=lambda _s: None)


def _run(state, uid, stages, *, max_repairs):
    spec = _write_spec(state, uid)
    orch = _orch(state, stages)
    result = orch.start(RunConfig(goal="Phase8 QA 闭环", source="test", max_repairs=max_repairs,
                                  stages=["generate", "qa", "compose"]),
                        specs=[spec], background=False)
    assert result["jobs"] == [uid]
    return orch


# ── 场景 1：画面不合格 → 回退 generate，重复到上限 → BLOCKED（不死循环）──
def test_visual_failure_rewinds_generate_then_blocks_at_repair_limit(tmp_state):
    uid = "P8VIS"
    gen = _generate(tmp_state, uid)
    compose = _compose(tmp_state, uid)
    _write_evidence(tmp_state / "out" / f"gen_{uid}", uid,
                    {"video": GOOD_VIDEO, "spec": {"products_expected": 1},
                     "vision": {"products_seen": 2}})
    stages = {"generate": gen, "qa": stages_mod.stage_qa, "compose": compose}
    _run(tmp_state, uid, stages, max_repairs=2)

    job = store.get_job(uid)
    assert job["status"] == JobState.BLOCKED, job["status"]
    assert job["error_code"] == PRODUCT_DEFORMED

    # 每次 QA FAIL 都要回退 generate 重生：上限 2 → generate 共 3 次、qa 共 3 次
    assert gen.calls["n"] == 3, gen.calls
    repairs = store.list_repairs(uid)
    assert len(repairs) == 2
    assert all(r["action"] == "REGENERATE_SHOT" and r["rewind_to"] == "generate"
               for r in repairs)
    assert all(r["error_code"] == PRODUCT_DEFORMED for r in repairs)
    assert store.repair_summary(uid)["count"] == 2
    # "结果"也要落库：最后一次修复没能修好（被上限截断）→ FAILED
    assert repairs[-1]["status"] == "FAILED"
    assert store.repair_summary(uid)["by_code"] == {PRODUCT_DEFORMED: 2}

    # 到顶那一次必须明确标注 repair_exhausted，并转人工
    failures = [e for e in store.list_events(uid) if e["type"] == "stage_failed"]
    assert any((e.get("data") or {}).get("repair_exhausted") for e in failures)
    acts = [e for e in store.list_events(uid) if e["type"] == "repair_begin"]
    assert len(acts) == 2

    # QA 报告落盘（JSON 可机读 + Markdown 给人看）
    report_dir = tmp_state / "out" / f"gen_{uid}" / "qa"
    assert (report_dir / "qa_report_gen.json").is_file()
    assert "QA 报告" in (report_dir / "qa_report_gen.md").read_text(encoding="utf-8")
    payload = json.loads((report_dir / "qa_report_gen.json").read_text(encoding="utf-8"))
    assert payload["primary_error"] == PRODUCT_DEFORMED
    assert payload["passed"] is False


# ── 场景 2：字幕/ASR 类失败 → 只回退 compose 重建字幕，不重生视频 ──
def test_subtitle_failure_rewinds_compose_without_regenerating(tmp_state):
    uid = "P8SUB"
    gen = _generate(tmp_state, uid)
    compose = _compose(tmp_state, uid)
    _write_evidence(tmp_state / "out" / f"gen_{uid}", uid,
                    {"video": {"exists": True, "bytes": 150_000, "video_streams": 1,
                               "audio_streams": 1, "duration": 10.0},
                     "subtitle": {"cues": [{"start": 0.0, "end": 12.0, "text": "越界字幕"}]}})
    stages = {"generate": gen, "qa": stages_mod.stage_qa, "compose": compose}
    _run(tmp_state, uid, stages, max_repairs=3)

    assert gen.calls["n"] == 1, "字幕问题绝不允许重生视频"
    assert compose.calls["n"] == 1
    repairs = store.list_repairs(uid)
    assert len(repairs) == 1
    assert repairs[0]["action"] == "REBUILD_SUBTITLE"
    assert repairs[0]["rewind_to"] == "compose"
    assert repairs[0]["error_code"] == SUBTITLE_ALIGN_FAIL
    assert repairs[0]["stage"] == "qa"


# ── 场景 3：合规失败 → 直接人工，不烧一次重生 ──
def test_compliance_failure_goes_straight_to_human(tmp_state):
    uid = "P8CMP"
    gen = _generate(tmp_state, uid)
    compose = _compose(tmp_state, uid)
    _write_evidence(tmp_state / "out" / f"gen_{uid}", uid,
                    {"video": GOOD_VIDEO,
                     "copy": {"spoken": "本车续航 1000 公里，行业第一"}})
    stages = {"generate": gen, "qa": stages_mod.stage_qa, "compose": compose}
    _run(tmp_state, uid, stages, max_repairs=3)

    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert store.get_job(uid)["error_code"] == COMPLIANCE_BLOCK
    assert store.list_repairs(uid) == []
    assert gen.calls["n"] == 1, "合规问题不许靠重生绕过"


# ── 场景 4：修复预算跨 resume 累计（不许靠重新触发绕过上限）──
def test_repair_budget_survives_across_runs(tmp_state):
    uid = "P8BUDGET"
    gen = _generate(tmp_state, uid)
    compose = _compose(tmp_state, uid)
    _write_evidence(tmp_state / "out" / f"gen_{uid}", uid,
                    {"video": GOOD_VIDEO, "vision": {"products_seen": 2},
                     "spec": {"products_expected": 1}})
    stages = {"generate": gen, "qa": stages_mod.stage_qa, "compose": compose}
    orch = _run(tmp_state, uid, stages, max_repairs=1)
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert len(store.list_repairs(uid)) == 1

    # retry 再跑：预算已用 1/1 → 立刻转人工，不会再跑一轮生成
    before = gen.calls["n"]
    orch.retry(uid, background=False)
    assert gen.calls["n"] == before, "修复预算必须跨运行累计，不能被 retry 重置"
    assert store.get_job(uid)["status"] == JobState.BLOCKED
    assert len(store.list_repairs(uid)) == 1


# ── 场景 5：修复记录回填了真实成本与结果（PLANNED → EXECUTED / FAILED）──
def test_repair_records_backfill_cost_and_result(tmp_state):
    uid = "P8COST"
    gen = _generate(tmp_state, uid)
    compose = _compose(tmp_state, uid)
    _write_evidence(tmp_state / "out" / f"gen_{uid}", uid,
                    {"video": GOOD_VIDEO, "vision": {"products_seen": 2},
                     "spec": {"products_expected": 1}})
    stages = {"generate": gen, "qa": stages_mod.stage_qa, "compose": compose}
    _run(tmp_state, uid, stages, max_repairs=1)

    repairs = store.list_repairs(uid)
    assert repairs and repairs[0]["status"] in ("EXECUTED", "FAILED", "PLANNED")
    assert repairs[0]["cost"] is not None and repairs[0]["cost"] >= 0.0
    assert repairs[0]["attempt"] == 1 and repairs[0]["budget"] == 1
    done = [e for e in store.list_events(uid) if e["type"] == "repair_done"]
    assert done and "cost" in (done[-1].get("data") or {})
