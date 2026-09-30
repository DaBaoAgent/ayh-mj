"""发布配额/窗口/限流判断回归（Phase 0）。"""
from __future__ import annotations

from datetime import datetime

import pytest

from s6_publish import publish

pytestmark = pytest.mark.unit


class _FixedDatetime(datetime):
    """可控 now()。"""

    frozen = datetime(2026, 9, 30, 8, 0, 0)

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return cls.frozen


@pytest.fixture()
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "PACING_FILE", tmp_path / "pacing.json", raising=False)
    monkeypatch.setattr(publish, "datetime", _FixedDatetime, raising=False)
    _FixedDatetime.frozen = datetime(2026, 9, 30, 8, 0, 0)
    return _FixedDatetime


def test_quota_ok_inside_window(frozen):
    ok, reason = publish.check_quota("douyin")
    assert ok, reason


def test_quota_blocked_during_night_silence(frozen):
    frozen.frozen = datetime(2026, 9, 30, 23, 30, 0)
    ok, reason = publish.check_quota("douyin")
    assert not ok
    assert "静默" in reason


def test_quota_blocked_outside_publish_window(frozen):
    frozen.frozen = datetime(2026, 9, 30, 10, 30, 0)
    ok, reason = publish.check_quota("douyin")
    assert not ok
    assert "窗口" in reason


def test_quota_blocked_after_daily_limit(frozen, monkeypatch):
    monkeypatch.setattr(publish, "load_config", lambda: {"publish": {"daily_limit": 2}})
    publish.mark_published("douyin")
    publish.mark_published("douyin")
    ok, reason = publish.check_quota("douyin")
    assert not ok
    assert "上限" in reason


def test_quota_blocked_by_min_interval(frozen, monkeypatch):
    monkeypatch.setattr(
        publish, "load_config",
        lambda: {"publish": {"daily_limit": 10, "min_interval_minutes": 30}})
    publish.mark_published("douyin")
    frozen.frozen = datetime(2026, 9, 30, 8, 10, 0)  # +10 分钟
    ok, reason = publish.check_quota("douyin")
    assert not ok
    assert "分钟" in reason


def test_quota_blocked_when_platform_is_paused(frozen, tmp_path, monkeypatch):
    """Phase 10 任务 5：AUTH_EXPIRED 后平台被熔断暂停，任何路径都不许再发。"""
    from lib import packaging

    monkeypatch.setattr(publish, "ROOT", tmp_path, raising=False)
    packaging.pause_platform(tmp_path, "douyin", "登录失效（AUTH_EXPIRED）")
    ok, reason = publish.check_quota("douyin")
    assert not ok
    assert "暂停" in reason and "登录失效" in reason


def test_mark_published_increments_counter(frozen):
    publish.mark_published("douyin")
    publish.mark_published("douyin")
    pacing = publish.load_pacing()
    assert pacing["2026-09-30:douyin"] == 2
