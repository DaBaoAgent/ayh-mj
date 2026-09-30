"""Phase 10 单测 —— 自动互动护栏：每小时上限 / 冷却+抖动 / 查重 / 熔断。"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from lib.safety import EngageGuard, load_state, save_state, state_path

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 30, 10, 0, 0)


def _guard(**kw) -> EngageGuard:
    kw.setdefault("max_per_hour", 3)
    kw.setdefault("cooldown_seconds", 60)
    kw.setdefault("jitter_seconds", 30)
    kw.setdefault("dup_window", 5)
    kw.setdefault("circuit_threshold", 3)
    return EngageGuard({}, **kw)


def test_allows_when_fresh():
    ok, why = _guard().allow(now=T0)
    assert ok, why


def test_hourly_cap_blocks_then_recovers():
    g = _guard(max_per_hour=2)
    for i in range(2):
        g.record_reply("回一句", now=T0 + timedelta(minutes=10 * i))
    ok, why = g.allow(now=T0 + timedelta(minutes=30))
    assert not ok and "每小时上限" in why
    ok, _ = g.allow(now=T0 + timedelta(hours=1, minutes=1))
    assert ok


def test_cooldown_blocks_until_elapsed():
    g = _guard(cooldown_seconds=60, jitter_seconds=0)
    g.record_reply("回一句", now=T0)
    ok, why = g.allow(now=T0 + timedelta(seconds=30))
    assert not ok and "距上次回复" in why
    ok, _ = g.allow(now=T0 + timedelta(seconds=61))
    assert ok


def test_jitter_is_bounded_and_applied():
    g = _guard(cooldown_seconds=60, jitter_seconds=30)
    rng = random.Random(7)
    for _ in range(50):
        delay = g.next_delay(rng)
        assert 60 <= delay <= 90
    assert g.arm_jitter(random.Random(1)) >= 60
    g.record_reply("回一句", now=T0)
    # arm_jitter 之后冷却线被抬高到 cooldown + pending_jitter
    need = 60 + g.state["pending_jitter"]
    assert need > 60
    ok, why = g.allow(now=T0 + timedelta(seconds=60))
    assert not ok and f"需 {need:.0f}s" in why


def test_duplicate_reply_detection():
    g = _guard()
    g.record_reply("同一句回复", target="alice", now=T0)
    # 同一句话不管发给谁，都算重复（模板味最容易被判 spam）
    assert g.duplicate("同一句回复", target="alice")
    assert g.duplicate("同一句回复", target="bob")
    assert not g.duplicate("换个说法", target="alice")


def test_empty_reply_counts_as_duplicate():
    assert _guard().duplicate("   ")


def test_duplicate_window_is_bounded():
    g = _guard(dup_window=2)
    g.record_reply("一", now=T0)
    g.record_reply("二", now=T0)
    g.record_reply("三", now=T0)
    assert not g.duplicate("一")


def test_consecutive_failures_open_the_circuit():
    g = _guard(circuit_threshold=3)
    assert not g.record_failure("429")
    assert not g.record_failure("429")
    assert g.record_failure("登录失效")          # 第三次 → 刚刚熔断
    ok, why = g.allow(now=T0)
    assert not ok and "熔断" in why


def test_success_resets_failures_and_circuit():
    g = _guard(circuit_threshold=2)
    g.record_failure("x")
    g.record_failure("x")
    assert g.state["circuit_open"]
    g.reset_circuit()
    ok, _ = g.allow(now=T0)
    assert ok and not g.state["circuit_open"]


def test_record_reply_clears_failure_streak():
    g = _guard(circuit_threshold=3)
    g.record_failure("x")
    g.record_failure("x")
    g.record_reply("回一句", now=T0)
    assert g.state["failures"] == 0
    assert not g.state["circuit_open"]


def test_state_round_trips_through_disk(tmp_path):
    g = _guard()
    g.record_reply("回一句", target="alice", now=T0)
    g.record_failure("x")
    save_state(tmp_path, g.state)
    assert state_path(tmp_path).exists()
    again = EngageGuard(load_state(tmp_path))
    assert again.state["replies"] == [T0.strftime("%Y-%m-%d %H:%M:%S")]
    assert again.duplicate("回一句", target="alice")
    assert again.state["failures"] == 1


def test_missing_state_file_is_empty_not_an_error(tmp_path):
    assert load_state(tmp_path) == {}
    assert load_state(tmp_path / "nope") == {}
