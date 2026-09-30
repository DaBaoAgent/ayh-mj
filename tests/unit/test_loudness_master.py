"""Phase 9 单元 —— 统一响度/峰值口径与母线增益（必做 11）。

约定：
  · 阈值只有一份（lib/post/loudness.LOUDNESS_BAND / TRUE_PEAK_MAX / LOUDNESS_TARGET）；
  · 母线增益由**实测**响度算，峰值顶棚交给同源 alimiter；
  · 量不到 / 渲不出 → 不增益，只限幅（绝不让"测不到"变成"出不了片"）。
"""
from __future__ import annotations

import re

import pytest

from lib.post import loudness as L

pytestmark = pytest.mark.unit


def test_single_source_of_truth_thresholds():
    assert L.LOUDNESS_BAND == (-17.0, -9.0)
    assert L.TRUE_PEAK_MAX == -1.0
    assert L.LOUDNESS_BAND[0] < L.LOUDNESS_TARGET < L.LOUDNESS_BAND[1]
    assert L.LOUDNESS_TP < L.TRUE_PEAK_MAX, "限幅顶棚要严于验收上限"


def test_qa_checks_import_the_same_thresholds():
    from lib.qa import checks

    assert checks.LOUDNESS_BAND == L.LOUDNESS_BAND
    assert checks.TRUE_PEAK_MAX == L.TRUE_PEAK_MAX


def test_limiter_limit_is_derived_from_tp_not_hardcoded():
    m = re.search(r"limit=([0-9.]+)", L.limiter_filter())
    assert m, L.limiter_filter()
    assert float(m.group(1)) == pytest.approx(10 ** (L.LOUDNESS_TP / 20), abs=1e-3)
    assert "0.95" not in L.limiter_filter(), "旧的拍脑袋 0.95 不该再出现"


def test_master_gain_hits_target_from_measured_loudness():
    assert L.master_gain({"loudness_lufs": -26.1}) == pytest.approx(10.1, abs=0.01)
    assert L.master_gain({"loudness_lufs": -14.0}) == pytest.approx(-2.0, abs=0.01)
    assert L.master_gain({"loudness_lufs": -16.0}) == 0.0


def test_master_gain_is_guarded_when_unmeasured():
    assert L.master_gain({}) == 0.0
    assert L.master_gain({"error": "file not found"}) == 0.0
    assert L.master_gain({"loudness_lufs": -120.0}) == 18.0, "荒谬增益要被夹住"
    assert L.master_gain({"loudness_lufs": 40.0}) == -24.0


def test_in_band_and_issues_agree():
    ok = {"loudness_lufs": -16.0, "true_peak_db": -1.4}
    assert L.in_band(ok["loudness_lufs"], ok["true_peak_db"]) is True
    assert L.issues(ok) == []
    loud_off = {"loudness_lufs": -24.0, "true_peak_db": -1.4}
    assert L.in_band(loud_off["loudness_lufs"], loud_off["true_peak_db"]) is False
    assert L.issues(loud_off)
    hot = {"loudness_lufs": -16.0, "true_peak_db": 0.4}
    assert L.in_band(hot["loudness_lufs"], hot["true_peak_db"]) is False
    assert any("峰值" in x for x in L.issues(hot))


def test_issue_helpers_never_claim_a_verdict_without_measurement():
    empty: dict = {}
    assert L.in_band(None, None) is False
    assert L.issues(empty)
    assert "未测得" in L.summarize(empty)


def test_master_for_mix_falls_back_instead_of_raising(tmp_path):
    graph = "[0:a]anull[base];[base]anull[prem]"
    master, measured = L.master_for_mix(["ffmpeg-not-a-real-binary"], graph, tmp_path / "x.wav")
    assert master.startswith("volume=0dB")
    assert measured.get("loudness_lufs") is None
    assert not tmp_path.joinpath("x.wav").exists()


def test_sfx_bed_gain_is_measured_not_hardcoded(tmp_path):
    from lib.post import sfx

    assert sfx.asset_gain_db(tmp_path / "nope.mp3") is None
    # 兜底值必须仍然存在且是个正常量级（不再是 +26dB 那种）
    assert set(sfx._GAIN_DB) == {"ding", "whoosh", "pop", "beep"}
    assert all(-6 <= v <= 18 for v in sfx._GAIN_DB.values()), sfx._GAIN_DB
    assert sfx.SFX_BED_PEAK <= -6.0, "bed 峰值目标要明显低于人声母线"
