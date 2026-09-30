"""Phase 10 单测 —— 自动互动真的被护栏拦住（handle_comments / handle_dms 接线）。

只验证"接线正确"：限流、查重、熔断三件事实必须体现在 stats 上，
而不是让循环继续闷头回复（这正是平台风控最恨的行为）。
不联网：uploadpost 的调用被替换成假函数。
"""
from __future__ import annotations

import pytest

from lib.safety import EngageGuard

pytestmark = pytest.mark.unit


@pytest.fixture()
def engage(tmp_state, tmp_path, monkeypatch):
    """把 s6_publish.engage 的外部依赖全部换成假的（0 网络 0 付费）。"""
    from s6_publish import engage as mod

    monkeypatch.setattr(mod, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(mod, "already_handled", lambda cid: False, raising=False)
    monkeypatch.setattr(mod, "record", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(mod, "gen_reply", lambda text, context="comment": "一个正经回复",
                        raising=False)
    monkeypatch.setattr(mod, "review_reply", lambda reply, channel="engage": (True, ""),
                        raising=False)

    import s6_publish.uploadpost as up
    sent: list[tuple] = []
    monkeypatch.setattr(up, "comments", lambda *a, **k: {"comments": [
        {"id": "c1", "text": "奶奶用这个好方便啊", "user": {"username": "alice"}},
        {"id": "c2", "text": "这个看着真不错", "user": {"username": "bob"}},
    ]}, raising=False)
    monkeypatch.setattr(up, "create_comment",
                        lambda *a, **k: sent.append(a) or {"ok": True}, raising=False)

    def _install(guard: EngageGuard):
        monkeypatch.setattr(mod, "build_guard", lambda: guard, raising=False)

    mod._install_guard = _install
    mod._sent = sent
    return mod


def test_hourly_cap_limits_actual_replies(engage):
    engage._install_guard(EngageGuard({}, max_per_hour=1, cooldown_seconds=0,
                                      jitter_seconds=0, circuit_threshold=9))
    stats = engage.handle_comments("instagram", yes=True)
    assert stats["replied"] == 1
    assert stats["rate_limited"] == 1
    assert len(engage._sent) == 1


def test_duplicate_reply_is_never_sent_twice(engage):
    engage._install_guard(EngageGuard({}, max_per_hour=10, cooldown_seconds=0,
                                      jitter_seconds=0, circuit_threshold=9))
    stats = engage.handle_comments("instagram", yes=True)
    assert stats["replied"] == 1
    assert stats["duplicate"] == 1
    assert len(engage._sent) == 1


def test_consecutive_failures_open_the_circuit_and_stop(engage, monkeypatch):
    import s6_publish.uploadpost as up

    def boom(*_a, **_k):
        raise RuntimeError("429 too many requests")

    monkeypatch.setattr(up, "create_comment", boom, raising=False)
    engage._install_guard(EngageGuard({}, max_per_hour=10, cooldown_seconds=0,
                                      jitter_seconds=0, circuit_threshold=2))
    stats = engage.handle_comments("instagram", yes=True)
    assert stats["circuit_open"] is True
    assert stats["replied"] == 0
    assert len(engage._sent) == 0
    # 熔断后状态落盘：下一轮 run 也会被 allow() 直接拦下
    from lib.safety import load_state
    assert load_state(engage.ROOT)["circuit_open"] is True


def test_guard_state_is_persisted_after_a_run(engage):
    from lib.safety import load_state

    engage._install_guard(EngageGuard({}, max_per_hour=5, cooldown_seconds=0,
                                      jitter_seconds=0, circuit_threshold=9))
    stats = engage.handle_comments("instagram", yes=True)
    # 假 gen_reply 每次都返回同一句 → 第二条被查重拦下，只落一条记录
    assert stats["replied"] == 1 and stats["duplicate"] == 1
    assert len(load_state(engage.ROOT)["replies"]) == 1
