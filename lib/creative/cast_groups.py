"""角色组（Phase 5：从 tools/pick_combo.py 提上来，供 Planner 与 CLI 共用一份）。

`state/groups_used.json` 只记"组名 → 用过它的 job 列表"，是**保新特征**，不是规则。
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import STATE_DIR

ROOT = Path(__file__).resolve().parent.parent.parent
LIB_DIR = ROOT / "assets" / "cast" / "library"
GROUPS_STATE = STATE_DIR / "groups_used.json"

GROUP_DEFS: list[dict] = [
    {"name": "核心卡司", "prefix": "core_",
     "base": ["elder_portrait", "mother_portrait", "son_portrait", "courier_portrait", "dog_portrait"],
     "desc": "老王宇宙常驻（老王家人/亲友/社区）"},
    {"name": "城市组", "prefix": "city_", "base": [], "desc": "城市家庭与邻里日常"},
    {"name": "欧美组", "prefix": "western_", "base": [], "desc": "外国角色讲中文"},
    {"name": "时尚组", "prefix": "fashion_", "exclude": "fashion_western", "base": [],
     "desc": "时尚感人群（脑洞/时尚广告）"},
    {"name": "老外时尚组", "prefix": "fashion_western", "base": [], "desc": "老外时尚人群"},
]


def group_members(group: dict) -> list[str]:
    out = list(group.get("base") or [])
    prefix = group.get("prefix")
    if prefix:
        for f in sorted(LIB_DIR.glob(f"{prefix}*.png")):
            if group.get("exclude") and f.stem.startswith(group["exclude"]):
                continue
            out.append(f.stem)
    return out


def load_used() -> dict:
    if GROUPS_STATE.exists():
        try:
            return json.loads(GROUPS_STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_used(used: dict) -> None:
    GROUPS_STATE.parent.mkdir(parents=True, exist_ok=True)
    GROUPS_STATE.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")


def record_group(name: str, tag: str) -> None:
    used = load_used()
    lst = used.setdefault(name, [])
    if tag not in lst:
        lst.append(tag)
    save_used(used)


def use_counts() -> dict:
    used = load_used()
    return {g["name"]: len(used.get(g["name"], [])) for g in GROUP_DEFS}


def pick_group(name: str | None = None, *, exclude: tuple[str, ...] = ()) -> dict:
    """选角色组：指定优先；否则在"今天没用过"的组里挑使用次数最少的。"""
    if name:
        for g in GROUP_DEFS:
            if g["name"] == name:
                return g
        raise KeyError(f"未知角色组: {name}（可选: {[g['name'] for g in GROUP_DEFS]}）")
    used = use_counts()
    pool = [g for g in GROUP_DEFS if g["name"] not in set(exclude)] or list(GROUP_DEFS)
    return min(pool, key=lambda g: (used.get(g["name"], 0), g["name"]))
