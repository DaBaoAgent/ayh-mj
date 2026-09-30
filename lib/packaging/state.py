"""Packaging artifact 与平台暂停状态的落盘位置（Phase 10）。

两件事实必须只有一个来源：
  · 每条视频的 packaging brief → `out/gen_<uid>/packaging.json`（与 spec/成片同目录）；
  · 平台暂停（AUTH_EXPIRED / 账号异常）→ `state/publish_paused.json`，
    任何"真发"路径在选平台前都要先问这里，避免反复登录/反复发布。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BRIEF_FILENAME = "packaging.json"
PAUSE_FILENAME = "publish_paused.json"


def workspace_dir(root: str | Path, uid: str) -> Path:
    return Path(root) / "out" / f"gen_{uid}"


def packaging_path(root: str | Path, uid: str) -> Path:
    return workspace_dir(root, uid) / BRIEF_FILENAME


def save_brief(root: str | Path, uid: str, brief: dict) -> Path:
    path = packaging_path(root, uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_brief(root: str | Path, uid: str) -> dict | None:
    path = packaging_path(root, uid)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def pause_path(root: str | Path) -> Path:
    return Path(root) / "state" / PAUSE_FILENAME


def _read_pauses(root: str | Path) -> dict:
    try:
        data = json.loads(pause_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def paused_platforms(root: str | Path) -> dict:
    """{platform: {reason, at}} —— 只读。"""
    return _read_pauses(root)


def pause_reason(root: str | Path, platform: str) -> str:
    entry = _read_pauses(root).get(str(platform))
    if not entry:
        return ""
    if isinstance(entry, dict):
        return str(entry.get("reason") or "已暂停")
    return str(entry)


def pause_platform(root: str | Path, platform: str, reason: str) -> None:
    """暂停某平台（幂等）。AUTH_EXPIRED / 账号异常时必须立刻调用。"""
    data = _read_pauses(root)
    data[str(platform)] = {"reason": str(reason)[:300], "at": datetime.now().isoformat(timespec="seconds")}
    path = pause_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def resume_platform(root: str | Path, platform: str) -> bool:
    """人工确认后解除暂停；返回是否真的解除过。"""
    data = _read_pauses(root)
    if str(platform) not in data:
        return False
    data.pop(str(platform), None)
    path = pause_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
