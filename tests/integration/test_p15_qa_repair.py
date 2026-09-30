"""Phase 15.1 第 7/8/9 条 —— QA 四类缺陷识别 + 定点修复 + 上限收口。

  · 四类真实缺陷各自由 Critic 判定出**对应**的错误码：
    错嘴 → WRONG_SPEAKER、产品形变 → PRODUCT_DEFORMED、
    ASR 漏词 → ASR_MISMATCH、字幕失败 → SUBTITLE_ALIGN_FAIL；
  · RepairEngine 按 error_code 分派到不同动作与不同回退阶段
    （画面类回 generate、字幕类只回 compose，绝不重生视频）；
  · 修复到上限时必须 BLOCKED + repair_exhausted，绝不死循环。

证据由 `tests/p15_support.evidence()` 注入，判定走产线真实的 `lib.qa.critic`。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.creative import planner as planner_mod
from lib.creative.prescreen import needs_prescreen
from lib.jobstore import JobState
from lib.jobstore import store as jobstore
from lib.orchestrator import PLAYBOOK, RepairEngine, RunConfig, StageResult, plan_repair
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import (
    ASR_MISMATCH,
    CLAIM_FORBIDDEN,
    COMPLIANCE_BLOCK,
    DOWNLOAD_FAILED,
    PRODUCT_DEFORMED,
    PUBLISH_QUOTA,
    REQUIRE_HUMAN,
    SUBTITLE_ALIGN_FAIL,
    WRONG_SPEAKER,
)
from tests import p15_support as S

pytestmark = pytest.mark.integration

GOAL = "Phase15修复闭环"
# 字幕时间轴倒挂 → SUBTITLE_ALIGN_FAIL
BAD_SUBTITLE = {"cues": [{"start": 5.0, "end": 2.0, "text": "时间轴倒挂的字幕"}],
                "wrap_ok": True, "safe_area_ok": True}

DEFECTS = [
    ("错嘴", dict(wrong_speaker_shots=[1]), WRONG_SPEAKER, "REGENERATE_SHOT", "generate"),
    ("产品形变", dict(product_deformed=True, deformed_parts=["车架"]),
     PRODUCT_DEFORMED, "REGENERATE_SHOT", "generate"),
    ("ASR漏词", dict(transcript_text="只听见一句"), ASR_MISMATCH,
     "REBUILD_SUBTITLE", "compose"),
    ("字幕失败", dict(subtitle=BAD_SUBTITLE), SUBTITLE_ALIGN_FAIL,
     "REBUILD_SUBTITLE", "compose"),
]


@pytest.fixture(autouse=True)
def _no_autodl(monkeypatch):
    return S.no_real_autodl(monkeypatch)


@pytest.fixture()
def lines(monkeypatch):
    return S.install_lines(monkeypatch)


def _pick(tmp_state, *, need_lines: bool = False):
    """自主规划出一条低风险（不触发预筛）的稿子；ASR 用例还要它有台词。"""
    planned = planner_mod.plan_missing(store=jobstore, daily_target=6, count=6,
                                       queue_dir=tmp_state / "queue_15s",
                                       state_dir=tmp_state, goal=GOAL)
    for pj in planned:
        doc = json.loads(Path(pj.spec_path).read_text(encoding="utf-8"))
        if needs_prescreen(doc):
            continue
        if need_lines and not S.doc_lines(doc):
            continue
        return pj, doc
    raise AssertionError("这一批里没有可用的低风险稿子")


def _run(tmp_state, spec_path, doc, *, inject=None, max_repairs=1):
    """第一次验片注入缺陷、第二次干净；只有 compose 是 fixture 渲染。"""
    uid = spec_path.stem
    provider = S.new_provider()

    def qa_evidence_for(_uid, n):
        return S.evidence(doc, **(inject or {})) if n == 1 else S.evidence(doc)

    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider,
                                docs={uid: doc}, qa_evidence_for=qa_evidence_for)
    jobstore.create_job(goal=GOAL, uid=uid)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_repairs=max_repairs,
                    stages=list(stages_mod.STAGE_ORDER))
    res = orch.start(cfg, specs=[spec_path], background=False)
    return orch, provider, res


# ── ⑦ 四类缺陷各自被识别，并且修复落在正确的阶段 ──────────────────────
@pytest.mark.parametrize("label,inject,code,action,rewind", DEFECTS,
                         ids=[d[0] for d in DEFECTS])
def test_each_defect_class_is_detected_and_repaired_in_place(tmp_state, lines,
                                                             label, inject, code, action, rewind):
    pj, doc = _pick(tmp_state, need_lines=label in ("ASR漏词", "字幕失败"))
    orch, provider, res = _run(tmp_state, pj.spec_path, doc, inject=inject, max_repairs=1)
    assert res["ok"] is True, res

    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.READY, (label, job["status"], job["error_code"])

    repairs = jobstore.list_repairs(pj.uid)
    assert len(repairs) == 1, (label, repairs)
    got = repairs[0]
    assert got["error_code"] == code, (label, got["error_code"], got)
    assert got["action"] == action, (label, got["action"])
    assert got["rewind_to"] == rewind, (label, got["rewind_to"])
    assert got["stage"] == "qa", (label, got["stage"])
    assert got["status"] == "EXECUTED", got

    # 画面类回 generate（但成片已在 → 不重复付费）；字幕类只重跑 compose
    if rewind == "generate":
        assert orch.stages["generate"].calls["n"] == 2, label
    else:
        assert orch.stages["generate"].calls["n"] == 1, label
    assert provider.submit_count == 1, (label, provider.submitted)

    # QA 报告落盘；第一次验片的失败结论必须能在库里逐条追溯
    report_dir = tmp_state / "out" / f"gen_{pj.uid}" / "qa"
    assert (report_dir / "qa_report_gen.json").is_file()
    failures = [(e.get("data") or {}).get("error_code") for e in jobstore.list_events(pj.uid)
                if e["type"] == "stage_failed" and e.get("stage") == "qa"]
    assert code in failures, (label, failures)
    gen_reports = [bool(e["passed"]) for e in
                   jobstore.list_evaluations(pj.uid, "qa_report_gen")]
    if rewind == "generate":
        assert gen_reports == [False, True], (label, gen_reports)
    else:
        assert gen_reports == [False], (label, gen_reports)
        final_reports = [bool(e["passed"]) for e in
                         jobstore.list_evaluations(pj.uid, "qa_report_final")]
        assert final_reports == [True], (label, final_reports)


# ── ⑧ 同一张映射表：每个 error_code 有自己的动作与回退目标 ─────────────
def test_repair_engine_dispatches_every_error_code_to_its_own_action():
    expected = [
        (WRONG_SPEAKER, "REGENERATE_SHOT", "generate", "qa"),
        (PRODUCT_DEFORMED, "REGENERATE_SHOT", "generate", "qa"),
        (ASR_MISMATCH, "REBUILD_SUBTITLE", "compose", "qa"),
        (SUBTITLE_ALIGN_FAIL, "REBUILD_SUBTITLE", "compose", "qa"),
        (DOWNLOAD_FAILED, "RETRY_SAME", "", "generate"),
        (CLAIM_FORBIDDEN, REQUIRE_HUMAN, "", "preflight"),
        (PUBLISH_QUOTA, "WAIT_AND_RESUME", "", "publish"),
        (COMPLIANCE_BLOCK, REQUIRE_HUMAN, "", "preflight"),
    ]
    engine = RepairEngine()
    for code, action, rewind, stage in expected:
        decision = engine.decide(StageResult.fail(stage, code), attempts=1, max_attempts=3,
                                 stage=stage)
        plan = plan_repair(code, stage=stage, attempt=1)
        assert decision.action == action, (code, decision.action)
        assert plan.action == action and plan.rewind_to == rewind, (code, plan.to_dict())
        if code in PLAYBOOK:
            assert plan.instructions, (code, "登记过的码必须带可执行说明")


# ── ⑨ 修复到上限 → BLOCKED（不死循环、不重复烧钱）─────────────────────
def test_repair_limit_blocks_instead_of_looping_forever(tmp_state, lines):
    pj, doc = _pick(tmp_state)
    provider = S.new_provider()

    def always_bad(_uid, _n):
        return S.evidence(doc, product_deformed=True, deformed_parts=["车架"])

    orch = S.build_orchestrator(jobstore, tmp_state, provider=provider,
                                docs={pj.uid: doc}, qa_evidence_for=always_bad)
    jobstore.create_job(goal=GOAL, uid=pj.uid)
    cfg = RunConfig(goal=GOAL, source="test", daily_target=1, max_repairs=1,
                    stages=list(stages_mod.STAGE_ORDER))
    assert orch.start(cfg, specs=[pj.spec_path], background=False)["ok"] is True

    job = jobstore.get_job(pj.uid)
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == PRODUCT_DEFORMED, (job["error_code"], job["error"])
    assert orch.stages["qa"].calls[pj.uid] == 2, "上限 1 次 → QA 总共只该跑 2 次"
    assert orch.stages["generate"].calls["n"] == 2
    assert provider.submit_count == 1, "回退重跑必须复用已成片，不重复付费"
    assert float(job["cost_spent"]) == pytest.approx(0.9, abs=1e-6), job["cost_spent"]

    summary = jobstore.repair_summary(pj.uid)
    assert summary["count"] == 1 and summary["by_code"] == {PRODUCT_DEFORMED: 1}, summary
    exhausted = [e for e in jobstore.list_events(pj.uid)
                 if e["type"] == "stage_failed"
                 and (e.get("data") or {}).get("repair_exhausted")]
    assert exhausted, "到顶必须明确标注 repair_exhausted"
    assert exhausted[-1]["data"]["repairs_used"] == 1
    assert exhausted[-1]["data"]["repairs_limit"] == 1
    # 不给下游留下伪成功的成片
    assert not (tmp_state / "out" / f"gen_{pj.uid}" / "onetake_final.mp4").exists()
