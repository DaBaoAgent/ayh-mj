"""片型池（Genres）— 10 种片型轮换（2026-09-25 宝哥令：去掉「演示」后扩到 10 种）

选片时与 角色组/卖点/角度 一起做智能组合（tools/pick_combo.py）。
使用记录存 state/genres_used.json（保新优先）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "genres_used.json"

GENRES = [
    {"id": "G1", "name": "剧情短片", "dir": "单场景小故事+产品自然融入（T06/T07 型）", "shots": 4},
    {"id": "G2", "name": "短剧狗血爽文", "dir": "打脸/扮猪吃虎/攀比反转，强冲突快节奏（T11-T13 型）", "shots": 4},
    {"id": "G3", "name": "魔性广告", "dir": "记忆点重复洗脑+同动作×3+夸张表演（T14 型）", "shots": 4},
    {"id": "G4", "name": "脑洞广告", "dir": "巧思设定/拟人化/神转折（相亲角、脑洞10连型）", "shots": 4},
    {"id": "G5", "name": "情感故事", "dir": "亲情温情叙事，儿女视角送关怀（先抑后扬/泪点收）", "shots": 4},
    {"id": "G6", "name": "街访伪纪录", "dir": "手持采访体：路人被问爸妈出行话题，真实感钩子", "shots": 4},
    {"id": "G7", "name": "vlog生活流", "dir": "第一人称生活记录：老王的一天（陪伴感/真实感）", "shots": 5},
    {"id": "G8", "name": "反差喜剧", "dir": "无厘头夸张对比（壮汉vs奶奶等），纯搞笑路线", "shots": 4},
    {"id": "G9", "name": "悬念反转", "dir": "前3秒设悬念（神秘包裹/神秘来客），结尾揭晓", "shots": 4},
    {"id": "G10", "name": "对比评测", "dir": "两台车 PK/前后对比实验，数据说话（T09 型）", "shots": 4},
]


def _load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def used_count() -> dict:
    used = _load()
    return {g["id"]: len(used.get(g["id"], [])) for g in GENRES}


def next_genre() -> dict:
    """选使用次数最少的片型（并列时按序取先）"""
    used = _load()
    return min(GENRES, key=lambda g: len(used.get(g["id"], [])))


def record_genre(genre_id: str, tag: str) -> None:
    used = _load()
    lst = used.setdefault(genre_id, [])
    if tag not in lst:
        lst.append(tag)
    STATE.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    u = used_count()
    print("片型池（10 种）：")
    for g in GENRES:
        print(f"  {g['id']} {g['name']}（已用{u[g['id']]}次）— {g['dir']}")
    print("下一个推荐:", next_genre()["name"])
