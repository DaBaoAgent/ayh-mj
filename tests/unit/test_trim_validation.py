"""Phase 9 单元 —— trim_onetake 裁剪校验：局部失败不得静默跳过（必做任务 5）。

用假的 ffmpeg/ffprobe 层驱动，验证「段数 / 时长 / 音视频流」三类校验都会拦住坏输出。
"""
from __future__ import annotations

import types
from pathlib import Path

import pytest

import tools.trim_onetake as TR

pytestmark = pytest.mark.unit


class _Result:
    def __init__(self, rc: int = 0) -> None:
        self.returncode = rc
        self.stdout = ""
        self.stderr = ""


def _install(monkeypatch, *, fail_index=None, out_probe=None, source_probe=None):
    source_probe = source_probe or {"duration": 4.0, "video": 1, "audio": 1}
    out_probe = out_probe or {"duration": 3.15, "video": 1, "audio": 1}

    def fake_run(cmd, **_kw):
        out = Path(cmd[-1])
        if out.name.startswith("seg_"):
            idx = int(out.name.split("_")[1].split(".")[0])
            if fail_index is not None and idx == fail_index:
                return _Result(1)
            out.write_bytes(b"x" * 4096)
            return _Result(0)
        out.write_bytes(b"x" * 4096)
        return _Result(0)

    def fake_probe(path):
        name = Path(path).name
        if name.startswith("seg_"):
            return {"duration": 1.0, "video": 1, "audio": 1}
        if name.endswith("_trim.mp4"):
            return dict(out_probe)
        return dict(source_probe)

    monkeypatch.setattr(TR, "subprocess",
                        types.SimpleNamespace(run=fake_run, SubprocessError=Exception))
    monkeypatch.setattr(TR, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(TR, "ffprobe", lambda: "ffprobe")
    monkeypatch.setattr(TR, "_probe", fake_probe)


def _video(tmp_path: Path) -> Path:
    v = tmp_path / "onetake.mp4"
    v.write_bytes(b"x" * 8192)
    return v


def test_valid_trim_passes_all_checks(monkeypatch, tmp_path):
    _install(monkeypatch, out_probe={"duration": 2.0, "video": 1, "audio": 1})
    report = TR.apply_keep(_video(tmp_path), [(0.0, 1.0), (2.0, 3.0)], tmp_path / "onetake_trim.mp4")
    assert report["ok"] is True
    assert report["parts_produced"] == report["parts_expected"] == 2
    assert report["video_streams"] == 1 and report["audio_streams"] == 1
    assert report["errors"] == []


def test_failed_segment_is_never_silently_dropped(monkeypatch, tmp_path):
    _install(monkeypatch, fail_index=0, out_probe={"duration": 1.0, "video": 1, "audio": 1})
    report = TR.apply_keep(_video(tmp_path), [(0.0, 1.0), (2.0, 3.0)], tmp_path / "onetake_trim.mp4",
                           tolerance=0.2)
    assert report["ok"] is False
    assert report["parts_produced"] == 1 and report["parts_expected"] == 2
    assert any("局部 ffmpeg 失败" in e for e in report["errors"])
    assert any("产出段数" in e for e in report["errors"])


def test_missing_audio_stream_is_rejected(monkeypatch, tmp_path):
    _install(monkeypatch, out_probe={"duration": 3.15, "video": 1, "audio": 0})
    report = TR.apply_keep(_video(tmp_path), [(0.85, 4.0)], tmp_path / "onetake_trim.mp4")
    assert report["ok"] is False
    assert any("音频流" in e for e in report["errors"])


def test_duration_mismatch_is_rejected(monkeypatch, tmp_path):
    _install(monkeypatch, out_probe={"duration": 1.0, "video": 1, "audio": 1})
    report = TR.apply_keep(_video(tmp_path), [(0.85, 4.0)], tmp_path / "onetake_trim.mp4")
    assert report["ok"] is False
    assert any("时长" in e for e in report["errors"])


def test_empty_keep_is_rejected(monkeypatch, tmp_path):
    _install(monkeypatch)
    report = TR.apply_keep(_video(tmp_path), [], tmp_path / "onetake_trim.mp4")
    assert report["ok"] is False
    assert any("保留段为空" in e for e in report["errors"])


def test_main_exits_nonzero_when_validation_fails(monkeypatch, tmp_path):
    _install(monkeypatch, fail_index=0)
    monkeypatch.setattr(TR, "probe_silences", lambda _v: (4.0, [(0.0, 1.0)]))
    monkeypatch.setattr(TR.sys, "argv", ["trim_onetake.py", str(_video(tmp_path)), "--apply"])
    with pytest.raises(SystemExit) as exc:
        TR.main()
    assert exc.value.code == 1


def test_main_succeeds_and_reports_validated_output(monkeypatch, tmp_path, capsys):
    _install(monkeypatch, out_probe={"duration": 3.15, "video": 1, "audio": 1})
    monkeypatch.setattr(TR, "probe_silences", lambda _v: (4.0, [(0.0, 1.0)]))
    monkeypatch.setattr(TR.sys, "argv", ["trim_onetake.py", str(_video(tmp_path)), "--apply"])
    TR.main()
    out = capsys.readouterr().out
    assert "1/1 段" in out and "3.15s" in out
