"""安全护栏（Phase 10）：自动互动的限流/查重/熔断。"""
from __future__ import annotations

from .engage_guard import (
    DEFAULT_CIRCUIT_THRESHOLD,
    DEFAULT_COOLDOWN,
    DEFAULT_DUP_WINDOW,
    DEFAULT_JITTER,
    DEFAULT_MAX_PER_HOUR,
    EngageGuard,
    load_state,
    save_state,
    state_path,
)

__all__ = [
    "DEFAULT_CIRCUIT_THRESHOLD", "DEFAULT_COOLDOWN", "DEFAULT_DUP_WINDOW", "DEFAULT_JITTER",
    "DEFAULT_MAX_PER_HOUR", "EngageGuard", "load_state", "save_state", "state_path",
]
