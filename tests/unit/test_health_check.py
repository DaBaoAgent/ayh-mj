"""能力体检回归（Phase 1）。

约束：
  · 缺能力时给出 DEGRADED / BLOCKED + 原因，而不是 import crash；
  · 必需能力缺失 → 总状态 BLOCKED；
  · 只有可选能力缺失 → DEGRADED；
  · 报告结构稳定（WebUI /api/state、bootstrap 都消费它）。
"""
from __future__ import annotations

import pytest

from tools import health_check

pytestmark = pytest.mark.unit


def test_run_health_shape():
    report = health_check.run_health()
    assert report["status"] in {health_check.READY, health_check.DEGRADED, health_check.BLOCKED}
    assert isinstance(report["root"], str) and report["root"]
    assert isinstance(report["blocking"], list)
    assert isinstance(report["degraded"], list)
    names = {c["name"] for c in report["capabilities"]}
    # 阶段要求：至少输出 python/ffmpeg/ffprobe/font/whisper/autodl/deepseek/
    # douyin_profile/postflow/upload_post/db/disk
    for required in ("python", "ffmpeg", "font", "whisper", "autodl", "deepseek",
                     "douyin_profile", "postflow", "upload_post", "db", "disk"):
        assert required in names, f"capability matrix 缺少 {required}"
    for cap in report["capabilities"]:
        assert set(cap) >= {"name", "status", "detail", "required", "fix"}
        assert cap["status"] in {health_check.READY, health_check.DEGRADED, health_check.BLOCKED}


def test_no_crash_when_ffmpeg_missing(monkeypatch):
    def _boom():
        raise FileNotFoundError("ffmpeg 不在 PATH")

    monkeypatch.setattr("lib.tools.ffmpeg", _boom, raising=False)
    monkeypatch.setattr("lib.tools.ffprobe", _boom, raising=False)
    cap = health_check.check_ffmpeg()
    assert cap["status"] == health_check.BLOCKED
    assert "ffmpeg" in cap["detail"].lower() or "ffmpeg" in cap["detail"]
    assert cap["fix"]


def test_missing_required_capability_blocks_overall(monkeypatch):
    monkeypatch.setattr(
        health_check, "check_ffmpeg",
        lambda: health_check._cap("ffmpeg", health_check.BLOCKED, "缺失", fix="装 ffmpeg"))
    report = health_check.run_health()
    assert report["status"] == health_check.BLOCKED
    assert "ffmpeg" in report["blocking"]


def test_optional_missing_degrades_not_blocks(monkeypatch):
    for name in ("check_ffmpeg", "check_python", "check_db"):
        monkeypatch.setattr(
            health_check, name,
            lambda n=name: health_check._cap(n.replace("check_", ""), health_check.READY, "ok"))
    monkeypatch.setattr(
        health_check, "check_postflow",
        lambda: health_check._cap("postflow", health_check.DEGRADED, "未安装",
                                  required=False, fix="安装 PostFlow"))
    report = health_check.run_health()
    assert report["status"] == health_check.DEGRADED
    assert report["blocking"] == []
    assert "postflow" in report["degraded"]


def test_format_report_contains_status_and_fixes():
    report = health_check.run_health()
    text = health_check.format_report(report)
    assert report["status"] in text
    assert "阻塞" in text and "降级" in text


def test_capability_probe_never_raises_on_broken_dependency(monkeypatch):
    """依赖损坏时该能力降级，绝不把异常抛给调用方。"""
    import sqlite3

    def _boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", _boom)
    cap = health_check.check_db()
    assert cap["status"] == health_check.BLOCKED
