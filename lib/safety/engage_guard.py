"""自动互动的安全护栏（Phase 10 任务 10）。

四道闸，任何一道都没过就不许回复：
  ① 每小时上限（`max_replies_per_hour`）—— 滚动 1 小时窗口，超了就等；
  ② 最小 + 随机安全间隔（`reply_cooldown_seconds` + `0..jitter`）—— 固定节奏最像机器人；
  ③ 重复回复检测 —— 同一句话在最近 N 条里重复出现即拦（模板味最容易被判 spam）；
  ④ 熔断 —— 连续 N 次失败（429/登录失效/接口异常）立刻停，不再继续撞平台风控。

状态落在 `state/engage_state.json`（本机运行态，不进仓库）。纯逻辑 + 一个文件，
方便测试直接喂时间戳与随机源，不依赖 sleep。
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

STATE_FILENAME = "engage_state.json"
_TS_FMT = "%Y-%m-%d %H:%M:%S"

DEFAULT_MAX_PER_HOUR = 20
DEFAULT_COOLDOWN = 60
DEFAULT_JITTER = 90
DEFAULT_DUP_WINDOW = 50
DEFAULT_CIRCUIT_THRESHOLD = 3


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.strptime(str(ts), _TS_FMT)
    except (TypeError, ValueError):
        return None


def state_path(root: str | Path) -> Path:
    return Path(root) / "state" / STATE_FILENAME


def load_state(root: str | Path) -> dict:
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(root: str | Path, state: dict) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


class EngageGuard:
    """滚动窗口限流 + 查重 + 熔断。所有判断都是纯函数式的（可注入 now/rng）。"""

    def __init__(self, state: dict | None = None, *, max_per_hour: int = DEFAULT_MAX_PER_HOUR,
                 cooldown_seconds: int = DEFAULT_COOLDOWN, jitter_seconds: int = DEFAULT_JITTER,
                 dup_window: int = DEFAULT_DUP_WINDOW,
                 circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD) -> None:
        self.state = dict(state or {})
        self.state.setdefault("replies", [])      # ["YYYY-mm-dd HH:MM:SS", ...]
        self.state.setdefault("recent", [])       # [{"text":..,"target":..}, ...]
        self.state.setdefault("failures", 0)      # 连续失败计数
        self.state.setdefault("circuit_open", False)
        self.state.setdefault("circuit_reason", "")
        self.max_per_hour = max(1, int(max_per_hour))
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self.jitter_seconds = max(0, int(jitter_seconds))
        self.dup_window = max(1, int(dup_window))
        self.circuit_threshold = max(1, int(circuit_threshold))

    # ── 判定 ───────────────────────────────────────────────────
    def allow(self, *, now: datetime | None = None) -> tuple[bool, str]:
        """能不能现在回复。返回 (ok, reason)。"""
        if self.state.get("circuit_open"):
            return False, f"互动已熔断：{self.state.get('circuit_reason') or '账号异常'}"
        now = now or datetime.now()
        recent = [t for t in (_parse(x) for x in self.state["replies"]) if t]
        hour_ago = now - timedelta(hours=1)
        in_hour = [t for t in recent if t > hour_ago]
        if len(in_hour) >= self.max_per_hour:
            return False, (f"近一小时已回复 {len(in_hour)}/{self.max_per_hour} 条"
                            f"（每小时上限），暂停")
        if recent:
            last = max(recent)
            gap = (now - last).total_seconds()
            need = self.cooldown_seconds + self.state.get("pending_jitter", 0)
            if gap < need:
                return False, f"距上次回复仅 {gap:.0f}s（需 {need:.0f}s）"
        return True, "OK"

    def duplicate(self, text: str, *, target: str = "") -> bool:
        """最近 dup_window 条里出现过同一句话 → 视为重复。

        只看文本、不看对象：同一句回复反复出现在不同评论区，正是平台判定
        "模板化营销"的典型特征。`target` 保留给调用方记录来源，不参与判定。
        """
        text = str(text or "").strip()
        if not text:
            return True
        recent = self.state["recent"][-self.dup_window:]
        return any(str(r.get("text") or "").strip() == text for r in recent)

    def next_delay(self, rng: random.Random | None = None) -> float:
        """下一次回复前该等多久（冷却 + 随机安全间隔）。"""
        r = rng or random
        return float(self.cooldown_seconds + r.randint(0, self.jitter_seconds))

    def arm_jitter(self, rng: random.Random | None = None) -> float:
        """摇一次随机间隔并记进状态，供 allow() 使用（避免每次调用都重新摇）。"""
        delay = self.next_delay(rng)
        self.state["pending_jitter"] = max(0.0, delay - self.cooldown_seconds)
        return delay

    # ── 记录 ───────────────────────────────────────────────────
    def record_reply(self, text: str, *, target: str = "", now: datetime | None = None) -> None:
        now = now or datetime.now()
        self.state["replies"].append(now.strftime(_TS_FMT))
        self.state["replies"] = self.state["replies"][-500:]
        self.state["recent"].append({"text": str(text or ""), "target": str(target or "")})
        self.state["recent"] = self.state["recent"][-self.dup_window:]
        self.state["failures"] = 0

    def record_failure(self, reason: str = "") -> bool:
        """记一次失败；返回熔断是否**刚刚**被打开。"""
        self.state["failures"] = int(self.state.get("failures") or 0) + 1
        if self.state["failures"] >= self.circuit_threshold and not self.state.get("circuit_open"):
            self.state["circuit_open"] = True
            self.state["circuit_reason"] = str(reason or "连续失败")[:200]
            return True
        return False

    def record_success(self) -> None:
        self.state["failures"] = 0
        self.state["circuit_open"] = False
        self.state["circuit_reason"] = ""

    def reset_circuit(self) -> None:
        """人工确认账号恢复后手动复位。"""
        self.state["failures"] = 0
        self.state["circuit_open"] = False
        self.state["circuit_reason"] = ""
