"""SRT 时间格式 + 字幕拆行回归（Phase 0）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from s5_compose.burn_subtitles import _cn_to_arabic, _split_natural, _strip_punct
from tools.lines_to_srt import write_srt

pytestmark = pytest.mark.unit


def test_srt_timestamp_format(tmp_path: Path):
    out = tmp_path / "a.srt"
    write_srt([(0.0, 1.234, "第一句"), (65.5, 3661.007, "第二句")], out)
    text = out.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,234" in text
    assert "00:01:05,500 --> 01:01:01,007" in text
    assert text.startswith("1\n")


def test_srt_roundtrip_indices(tmp_path: Path):
    out = tmp_path / "b.srt"
    write_srt([(0, 1, "甲"), (1, 2, "乙"), (2, 3, "丙")], out)
    blocks = out.read_text(encoding="utf-8").strip().split("\n\n")
    assert [b.splitlines()[0] for b in blocks] == ["1", "2", "3"]


def test_strip_punct_removes_chinese_and_ascii_punctuation():
    assert _strip_punct("你好，世界！a.b,c") == "你好世界abc"


def test_cn_to_arabic_converts_spec_numbers():
    assert "13.8" in _cn_to_arabic("十三点八公斤")
    assert "100" in _cn_to_arabic("承重一百公斤")


def test_split_natural_caps_line_length():
    chunks = _split_natural("邻居家老王又换了一台新车特别威风", max_chars=10)
    assert len(chunks) >= 2
    for c in chunks:
        assert c
        assert "，" not in c and "。" not in c


def test_split_natural_honours_speaker_separator():
    chunks = _split_natural("老王说｜那你呢", max_chars=10)
    assert len(chunks) == 2


def test_split_natural_short_line_unchanged():
    assert _split_natural("你好", max_chars=10) == ["你好"]
