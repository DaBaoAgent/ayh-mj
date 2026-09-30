"""Phase 8 —— QA 维度检查：≥8 种失败 fixture 各自映射到正确的 error_code。

对应计划 §Phase 8 必做任务 2（≥8 种失败 fixture 验证 repair routing）。
每一组证据都是"机器可读 dict"，与 `qa_evidence_<uid>.json` 共用同一 schema。
"""
from __future__ import annotations

import pytest

from lib.orchestrator.errors import (
    ASR_MISMATCH,
    COMPLIANCE_BLOCK,
    DOWNLOAD_FAILED,
    HUMAN_ANATOMY_FAIL,
    PRODUCT_DEFORMED,
    QA_FAILED,
    SUBTITLE_ALIGN_FAIL,
    VISUAL_QA_FAIL,
    WRONG_SPEAKER,
)
from lib.qa import checks

pytestmark = pytest.mark.unit


def _codes(findings) -> set[str]:
    return {f.error_code for f in findings if f.failed}


GOOD_VIDEO = {"exists": True, "bytes": 150_000, "video_streams": 1,
              "audio_streams": 1, "duration": 15.0}


# ── fixture 矩阵：证据 → 期望 error_code（这是 repair routing 的第一段）──────
FAILURE_FIXTURES = [
    # 1) 产品数量漂移
    ("product_count_drift",
     {"vision": {"products_seen": 2}, "spec": {"products_expected": 1}},
     PRODUCT_DEFORMED),
    # 2) 产品形变
    ("product_deformed",
     {"vision": {"product_deformed": True, "deformed_parts": ["瓶身"]}},
     PRODUCT_DEFORMED),
    # 3) 人体结构畸形
    ("human_anatomy_fail",
     {"vision": {"anatomy_ok": False, "anatomy_issues": ["多指", "腿穿模"]}},
     HUMAN_ANATOMY_FAIL),
    # 4) 说话人与声音不匹配
    ("wrong_speaker",
     {"vision": {"wrong_speaker_shots": [2]}},
     WRONG_SPEAKER),
    # 5) ASR 真实漏词
    ("asr_real_missing_word",
     {"spec": {"expected_lines": [{"shot": 1, "text": "今天带你去看新车"}]},
      "transcript": {"text": "今天带你去看新"}},
     ASR_MISMATCH),
    # 6) 字幕越界
    ("subtitle_out_of_bounds",
     {"video": {"exists": True, "bytes": 150_000, "video_streams": 1,
                "audio_streams": 1, "duration": 10.0},
      "subtitle": {"cues": [{"start": 0.0, "end": 12.0, "text": "越界字幕"}]}},
     SUBTITLE_ALIGN_FAIL),
    # 7) 留存：钩子太晚
    ("hook_too_late",
     {"vision": {"first_hook_seconds": 4.0}},
     VISUAL_QA_FAIL),
    # 8) 合规：未登记的产品承诺
    ("unregistered_claim",
     {"copy": {"spoken": "本车续航 1000 公里，行业第一"}},
     COMPLIANCE_BLOCK),
    # 9) 成片缺失（下载失败）
    ("artifact_missing",
     {"video": {"exists": False}},
     DOWNLOAD_FAILED),
    # 10) 成片没有视频流（编码损坏）
    ("no_video_stream",
     {"video": {"exists": True, "bytes": 200_000, "video_streams": 0},
      "spec": {"duration": 15}},
     QA_FAILED),
]


@pytest.mark.parametrize("name,evidence,expected", FAILURE_FIXTURES,
                         ids=[c[0] for c in FAILURE_FIXTURES])
def test_every_failure_fixture_maps_to_expected_error_code(name, evidence, expected):
    findings, dims, _ = checks.run_checks(evidence)
    assert expected in _codes(findings), f"{name} 未产出 {expected}：{_codes(findings)}"
    assert "fail" in dims.values()


def test_matrix_covers_at_least_eight_distinct_failure_modes():
    assert len(FAILURE_FIXTURES) >= 8
    assert len({c[2] for c in FAILURE_FIXTURES}) >= 6      # 至少 6 个不同 error_code


# ── 单维度细节（阈值边界与 severity）──────────────────────────────
def test_product_drift_reports_shots_and_fix_hint():
    f = checks.check_product({"vision": {"product_drift_shots": [3, 5]}})
    assert _codes(f) == {PRODUCT_DEFORMED}
    assert f[0].shot == 3 and f[0].fix_hint


def test_people_count_drift_is_visual_qa_fail():
    f = checks.check_cast({"vision": {"people_seen": 3}, "spec": {"people_expected": 2}})
    assert _codes(f) == {VISUAL_QA_FAIL}


def test_non_speaker_mouth_open_is_wrong_speaker():
    f = checks.check_cast({"vision": {"non_speaker_mouth_open": True}})
    assert _codes(f) == {WRONG_SPEAKER}


def test_homophone_is_only_a_warning_not_a_failure():
    ev = {"spec": {"expected_lines": [{"shot": 1, "text": "续航"}]},
          "transcript": {"text": "续杭", "homophones": ["续航"]}}
    f = checks.check_audio(ev)
    assert _codes(f) == set()
    assert any(x.severity == "WARN" for x in f)


def test_subtitle_overlap_and_orphan_lines():
    ev = {"video": {"duration": 10.0},
          "subtitle": {"cues": [{"start": 0.0, "end": 4.0, "text": "第一句"},
                                {"start": 3.0, "end": 6.0, "text": "第二句"}],
                       "orphan_lines": ["啊"]}}
    f = checks.check_audio(ev)
    assert SUBTITLE_ALIGN_FAIL in _codes(f)
    assert any(x.severity == "WARN" for x in f)


def test_subtitle_over_max_chars_without_wrap():
    ev = {"subtitle": {"cues": [{"start": 0.0, "end": 1.0, "text": "这是一句特别长的字幕超过安全区字数"}]}}
    f = checks.check_audio(ev)
    assert _codes(f) == {SUBTITLE_ALIGN_FAIL}


def test_retention_static_and_late_payoff():
    ev = {"video": {"duration": 15.0},
          "vision": {"first_hook_seconds": 1.0, "static_seconds": 3.0,
                     "payoff_seconds": 14.0}}
    f = checks.check_retention(ev)
    assert _codes(f) == {VISUAL_QA_FAIL}


def test_dialogue_without_audio_stream_is_qa_failed():
    ev = {"video": {"exists": True, "bytes": 150_000, "video_streams": 1,
                    "audio_streams": 0, "duration": 15.0},
          "spec": {"dialogue_mode": "dialogue", "duration": 15}}
    assert _codes(checks.check_delivery(ev)) == {QA_FAILED}


def test_duration_drift_is_qa_failed():
    ev = {"video": {"exists": True, "bytes": 150_000, "video_streams": 1,
                    "audio_streams": 1, "duration": 9.0},
          "spec": {"duration": 15}}
    assert _codes(checks.check_delivery(ev)) == {QA_FAILED}


def test_loudness_and_peak_are_only_warnings():
    ev = {"video": {"exists": True, "bytes": 150_000, "video_streams": 1,
                    "audio_streams": 1, "duration": 15.0,
                    "loudness_lufs": -3.0, "true_peak_db": 0.5},
          "spec": {"duration": 15}}
    f = checks.check_delivery(ev)
    assert _codes(f) == set()
    assert len([x for x in f if x.severity == "WARN"]) == 2


def test_missing_evidence_is_skipped_never_passed():
    findings, dims, notes = checks.run_checks(
        {}, dimensions=("product", "cast", "retention"))
    assert set(dims.values()) == {"skipped"}
    assert findings == []
    assert checks.coverage(dims) == 0.0
    assert sum(1 for n in notes if "未检查" in n) == 3


def test_delivery_missing_artifact_fails_rather_than_skips():
    findings, dims, _ = checks.run_checks({}, dimensions=("delivery",))
    assert dims["delivery"] == "fail"
    assert _codes(findings) == {DOWNLOAD_FAILED}


def test_rich_failure_counts_against_multiple_dimensions():
    ev = {"video": GOOD_VIDEO,
          "spec": {"duration": 15, "products_expected": 1, "people_expected": 1},
          "vision": {"products_seen": 2, "people_seen": 3, "first_hook_seconds": 5.0},
          "copy": {"spoken": "绝对最好用"}}
    findings, dims, _ = checks.run_checks(ev)
    assert {PRODUCT_DEFORMED, VISUAL_QA_FAIL, COMPLIANCE_BLOCK} <= _codes(findings)
    assert checks.coverage(dims) >= 0.5
