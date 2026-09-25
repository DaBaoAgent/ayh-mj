"""智能组合选择器 — 角色组 × 卖点 × 角度 × 片型（保新优先，2026-09-25 宝哥令）

出片标准流程第一步：每出一条片都先跑本工具选组合（模板已停用，除非宝哥指定）。

用法:
  python tools/pick_combo.py                      # 全自动选一套组合
  python tools/pick_combo.py --genre G4           # 指定片型
  python tools/pick_combo.py --group 时尚组        # 指定角色组
  python tools/pick_combo.py --point shock_18     # 指定卖点
  python tools/pick_combo.py --angle B20          # 指定角度
  python tools/pick_combo.py --new                # 只从"从未用过"里选（默认即保新）
输出: 组合方案（打印）+ state/combo_<时间戳>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles as angles_mod, genres, products

LIB = ROOT / "assets/cast/library"
GROUPS_USED = ROOT / "state" / "groups_used.json"
ANGLES_USED = ROOT / "state" / "story_angles_used.json"

GROUP_DEFS = [
    {"name": "核心卡司", "prefix": "core_", "base": ["elder_portrait", "mother_portrait", "son_portrait", "courier_portrait", "dog_portrait"], "desc": "老王宇宙常驻（老王家人/亲友/社区）"},
    {"name": "城市组", "prefix": "city_", "base": [], "desc": "城市家庭与邻里日常"},
    {"name": "欧美组", "prefix": "western_", "base": [], "desc": "外国角色讲中文"},
    {"name": "时尚组", "prefix": "fashion_", "exclude": "fashion_western", "base": [], "desc": "时尚感人群（脑洞/时尚广告）"},
    {"name": "老外时尚组", "prefix": "fashion_western", "base": [], "desc": "老外时尚人群"},
]


def group_members(g: dict) -> list[str]:
    out = list(g.get("base", []))
    if g["prefix"]:
        for f in sorted(LIB.glob(f"{g['prefix']}*.png")):
            if g.get("exclude") and f.stem.startswith(g["exclude"]):
                continue
            out.append(f.stem)
    return out


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def pick_group(name: str | None) -> dict:
    used = load_json(GROUPS_USED, {})
    if name:
        for g in GROUP_DEFS:
            if g["name"] == name:
                return g
        raise SystemExit(f"未知角色组: {name}（可选: {[g['name'] for g in GROUP_DEFS]}）")
    return min(GROUP_DEFS, key=lambda g: len(used.get(g["name"], [])))


def pick_angle(aid: str | None) -> dict:
    used = load_json(ANGLES_USED, {})
    pool = angles_mod.ANGLES if hasattr(angles_mod, "ANGLES") else None
    if pool is None:
        # 兼容：从模块里找列表
        for v in vars(angles_mod).values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0]:
                pool = v
                break
    if aid:
        for a in pool:
            if a["id"] == aid:
                return a
        raise SystemExit(f"未知角度: {aid}")
    fresh = [a for a in pool if not used.get(a["id"]) and not a.get("used_up")]
    return (fresh or pool)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group")
    ap.add_argument("--point")
    ap.add_argument("--angle")
    ap.add_argument("--genre")
    ap.add_argument("--commit", metavar="TAG", help="记录四池使用（tag=job uid），防止下条片重复")
    args = ap.parse_args()

    g = pick_group(args.group)
    members = group_members(g)

    if args.point:
        pt = next(p for p in products.SALES_POINTS if p["id"] == args.point)
    else:
        pt = products.next_point("")  # 全池选最少用

    ag = pick_angle(args.angle)

    if args.genre:
        gr = next(x for x in genres.GENRES if x["id"] == args.genre)
    else:
        gr = genres.next_genre()

    combo = {
        "picked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "group": {"name": g["name"], "count": len(members), "members": members, "desc": g["desc"]},
        "point": pt,
        "angle": ag,
        "genre": gr,
    }
    out = ROOT / f"state/combo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(combo, ensure_ascii=False, indent=1), encoding="utf-8")

    print("🎯 智能组合（保新优先）")
    print(f"  角色组: {g['name']}（{len(members)}人可选）— {g['desc']}")
    print(f"    成员样例: {', '.join(members[:8])}{' ...' if len(members) > 8 else ''}")
    print(f"  卖点:   {pt['id']} · {pt['name']} — {pt['hook']}")
    print(f"  角度:   {ag['id']} · {ag['name']} — {ag['dir']}")
    print(f"  片型:   {gr['id']} · {gr['name']} — {gr['dir']}（{gr['shots']}镜）")
    print(f"  方案已存: {out}")

    if args.commit:
        tag = args.commit
        used = load_json(GROUPS_USED, {})
        used.setdefault(g["name"], [])
        if tag not in used[g["name"]]:
            used[g["name"]].append(tag)
        GROUPS_USED.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")
        products.record_point(pt["id"], tag)
        angles_mod.record_angle(ag["id"], tag)
        genres.record_genre(gr["id"], tag)
        print(f"  ✅ 已记录四池使用（tag={tag}）：组/卖点/角度/片型 各+1")


if __name__ == "__main__":
    main()
