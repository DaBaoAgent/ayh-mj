"""Phase 8 —— QA 报告契约：结构化 JSON + 人类可读，且每个 FAIL 必须带 error_code。

对应计划 §Phase 8 必做任务 1（QA 输出结构化 JSON + 人类可读报告）。
"""
from __future__ import annotations

import json

import pytest

from lib.orchestrator.errors import (
    ASR_MISMATCH,
    COMPLIANCE_BLOCK,
    PRODUCT_DEFORMED,
    QA_FAILED,
    VISUAL_QA_FAIL,
)
from lib.qa.checks import coverage
from lib.qa.report import DIMENSIONS, QaFinding, QaReport

pytestmark = pytest.mark.unit


def _finding(dim="cast", sev="FAIL", code=VISUAL_QA_FAIL, msg="有问题", **kw):
    return QaFinding(dim, sev, code, msg, **kw)


def test_fail_finding_without_error_code_is_rejected():
    """计划硬要求：每个 FAIL 都要映射到一个 error_code，不许只有一句‘质量不好’。"""
    with pytest.raises(ValueError):
        QaFinding("cast", "FAIL", "", "只有一句主观结论")


def test_finding_rejects_unknown_dimension_and_severity():
    with pytest.raises(ValueError):
        QaFinding("nope", "FAIL", QA_FAILED, "x")
    with pytest.raises(ValueError):
        QaFinding("cast", "MAYBE", QA_FAILED, "x")


def test_score_penalizes_fail_and_warn_but_never_negative():
    clean = QaReport(dimensions=dict.fromkeys(DIMENSIONS, "pass"))
    assert clean.passed and clean.score() == 1.0

    one_fail = QaReport(findings=[_finding()])
    assert one_fail.failed and one_fail.score() == pytest.approx(0.65)

    only_warn = QaReport(findings=[_finding(sev="WARN")])
    assert only_warn.passed and only_warn.score() == pytest.approx(0.9)

    many = QaReport(findings=[_finding() for _ in range(4)])
    assert many.score() == 0.0


def test_codes_follow_primary_priority_and_dedup():
    rep = QaReport(findings=[
        _finding(dim="cast", code=VISUAL_QA_FAIL),
        _finding(dim="product", code=PRODUCT_DEFORMED),
        _finding(dim="compliance", code=COMPLIANCE_BLOCK),
        _finding(dim="cast", code=VISUAL_QA_FAIL),
    ])
    assert rep.codes() == [COMPLIANCE_BLOCK, PRODUCT_DEFORMED, VISUAL_QA_FAIL]
    assert rep.primary_error() == COMPLIANCE_BLOCK


def test_payload_keeps_error_code_for_every_fail():
    rep = QaReport(uid="U1", findings=[_finding(dim="audio", code=ASR_MISMATCH)])
    payload = rep.to_dict()
    assert payload["passed"] is False
    assert payload["primary_error"] == ASR_MISMATCH
    fails = [f for f in payload["findings"] if f["severity"] == "FAIL"]
    assert fails and all(f["error_code"] for f in fails)


def test_json_and_markdown_are_machine_and_human_readable():
    rep = QaReport(uid="U2", coverage=1.0,
                   dimensions={"product": "fail", "cast": "pass"},
                   findings=[_finding(dim="product", code=PRODUCT_DEFORMED,
                                      msg="产品形变", shot=3, fix_hint="重生问题镜")])
    md = rep.to_markdown()
    assert "QA 报告" in md and PRODUCT_DEFORMED in md and "重生问题镜" in md

    data = json.loads(rep.to_json())
    assert data["uid"] == "U2"
    assert data["score"] == rep.score()
    assert data["primary_error"] == PRODUCT_DEFORMED


def test_coverage_counts_only_actually_checked_dimensions():
    assert coverage({"product": "pass", "cast": "skipped", "audio": "fail"}) == 0.667
    assert coverage({}) == 0.0
    assert coverage({"product": "skipped"}) == 0.0


def test_summary_reports_primary_code_and_coverage():
    rep = QaReport(coverage=0.5, findings=[_finding(code=QA_FAILED)])
    text = rep.summary()
    assert "FAIL" in text and QA_FAILED in text and "50%" in text
