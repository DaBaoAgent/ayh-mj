"""Phase 9 单元 —— canonical transcript：一次 ASR、全链复用、字幕时间单一来源。

对应计划 §Phase 9 必做 1/2/4 与验收「一条视频只产生一个 canonical transcript」。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.post import transcript as T

pytestmark = pytest.mark.unit


class FakeAsr:
    """假转写器：按台词逐字给 0.2s 时间戳，并计数调用次数（用来证明"只推一次"）。"""

    def __init__(self, lines=("第一句话说走就走", "第二句其实没想到")):
        self.lines = list(lines)
        self.calls = 0

    def __call__(self, video):
        self.calls += 1
        segs, t = [], 0.5
        for line in self.lines:
            words = []
            for ch in line:
                words.append(T.Word(ch, round(t, 3), round(t + 0.2, 3)))
                t = round(t + 0.2, 3)
            segs.append(T.Segment(words[0].start, words[-1].end, line, words))
            t = round(t + 0.1, 3)
        return segs, {"model": "fake-medium", "language": "zh"}


def _video(tmp_path: Path, *, name: str = "onetake_trim.mp4", size: int = 4096):
    ws = tmp_path / "out" / "gen_U1"
    ws.mkdir(parents=True, exist_ok=True)
    v = ws / name
    v.write_bytes(b"x" * size)
    return ws, v


def test_ensure_runs_asr_exactly_once_and_reuses(tmp_path):
    ws, video = _video(tmp_path)
    asr = FakeAsr()
    tr1, reused1 = T.ensure(video, workspace=ws, transcriber=asr)
    tr2, reused2 = T.ensure(video, workspace=ws, transcriber=asr)

    assert asr.calls == 1, "第二次必须命中缓存，不得重推"
    assert reused1 is False and reused2 is True
    assert tr1.fingerprint() == tr2.fingerprint()
    assert tr1.has_word_timestamps


def test_reuse_invalidated_when_source_changes(tmp_path):
    ws, video = _video(tmp_path)
    asr = FakeAsr()
    T.ensure(video, workspace=ws, transcriber=asr)
    video.write_bytes(b"y" * 8192)          # 源视频变了 → 缓存失效
    T.ensure(video, workspace=ws, transcriber=asr)
    assert asr.calls == 2


def test_only_one_canonical_artifact_is_produced(tmp_path):
    ws, video = _video(tmp_path)
    T.ensure(video, workspace=ws, transcriber=FakeAsr())
    produced = sorted(p.name for p in (ws / "transcripts").iterdir())
    assert produced == ["canonical.json"], produced
    data = json.loads((ws / "transcripts" / "canonical.json").read_text(encoding="utf-8"))
    assert data["schema"] == "canonical-transcript/1.0"
    assert data["has_word_timestamps"] is True
    assert data["source"] == str(video.resolve())


def test_align_spans_uses_word_timestamps(tmp_path):
    ws, video = _video(tmp_path)
    asr = FakeAsr(lines=("第一句话说走就走", "第二句其实没想到"))
    tr, _ = T.ensure(video, workspace=ws, transcriber=asr)
    spans = T.align_spans(tr, list(asr.lines))
    assert len(spans) == 2
    assert spans[0] == (0.5, pytest.approx(0.5 + 0.2 * 8, abs=0.01))
    # 第二句必须严格在第一句结束之后（来自同一份时间轴）
    assert spans[1][0] >= spans[0][1]


def test_build_rows_splits_long_line_and_never_overlaps(tmp_path):
    ws, video = _video(tmp_path)
    line = "邻居家老王又换了一台新车特别威风"
    tr, _ = T.ensure(video, workspace=ws, transcriber=FakeAsr(lines=(line,)))
    rows = T.build_rows(tr, [line], max_chars=10)
    assert len(rows) >= 2, "长句必须拆行"
    for i, (a, b, text) in enumerate(rows):
        assert b > a
        assert text and "，" not in text
        if i:
            assert a >= rows[i - 1][1], "字幕不得重叠"


def test_load_returns_none_for_missing_or_corrupt(tmp_path):
    ws, video = _video(tmp_path)
    assert T.load(ws) is None
    path = T.canonical_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert T.load(ws) is None


def test_ensure_stub_upgrades_legacy_segments_without_asr(tmp_path):
    ws, video = _video(tmp_path)
    legacy = ws / "transcripts" / f"{video.stem}.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps([{"start": 0.0, "end": 1.0, "text": "老话说的好"}],
                                 ensure_ascii=False), encoding="utf-8")
    tr = T.ensure_stub(video, workspace=ws)
    assert tr.engine == "legacy"
    assert tr.segments and not tr.has_word_timestamps
    # 无字级时间也能给出对齐（按段落插值），保证下游不崩
    spans = T.align_spans(tr, ["老话说的好"])
    assert spans and spans[0][1] > spans[0][0]
