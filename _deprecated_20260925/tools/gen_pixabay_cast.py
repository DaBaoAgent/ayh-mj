"""Pixabay 真人素材：10 角色 × 4 候选 + 原角色图 → 对比网格

用法: .venv/Scripts/python.exe tools/gen_pixabay_cast.py
输出: assets/cast/compare_pixabay/<id>_候选网格.png（第1格=原AI图，2-5格=真人候选）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "assets/cast/library"
OUT = ROOT / "assets/cast/compare_pixabay"
CAND = ROOT / "assets/cast/pixabay"
OUT.mkdir(parents=True, exist_ok=True)

KEY = "15244830-e59ddba62e3c2403cba8c8ef8"

ROLES = {
    "city_grandpa_75": ["asian elderly man portrait", "chinese old man face"],
    "city_grandma_70": ["asian elderly woman portrait", "chinese old woman face"],
    "city_mom_45": ["asian woman 40s portrait", "chinese woman smiling portrait"],
    "city_young_man_30": ["asian young man portrait", "chinese man portrait"],
    "fashion_granny_silver": ["elegant elderly woman silver hair", "stylish senior woman"],
    "fashion_girl_20": ["asian young woman street fashion", "chinese girl portrait"],
    "western_grandpa_70": ["elderly man glasses portrait", "senior man white hair portrait"],
    "western_young_woman_28": ["young woman blonde portrait", "woman portrait smiling"],
    "city_boy_10": ["asian boy child portrait", "chinese boy smiling"],
    "fashion_gent_55": ["mature man suit portrait", "asian man suit portrait"],
}

PREF = ("asian", "chinese", "japan", "korea")


def search(q: str, n: int = 20) -> list[dict]:
    url = (f"https://pixabay.com/api/?key={KEY}&q={q.replace(' ', '+')}&image_type=photo"
           f"&orientation=vertical&per_page={n}&safesearch=true&order=popular")
    r = subprocess.run(["curl", "-s", "-m", "30", url], capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("hits", [])
    except Exception:  # noqa: BLE001
        return []


def pick(hits: list[dict], k: int = 4) -> list[dict]:
    pref = [h for h in hits if any(p in h.get("tags", "").lower() for p in PREF)]
    rest = [h for h in hits if h not in pref]
    out = pref + rest
    # 按宽高比≈竖版优先
    out.sort(key=lambda h: abs(h.get("imageHeight", 1) / max(h.get("imageWidth", 1), 1) - 1.5))
    return out[:k]


def grid(cid: str, paths: list[Path]) -> None:
    cells = []
    for p in [LIB / f"{cid}.png"] + paths:
        if p.exists():
            im = Image.open(p).convert("RGB")
            h = 560
            cells.append(im.resize((int(im.width * h / im.height), h)))
    if len(cells) < 2:
        return
    W = sum(c.width for c in cells) + 15 * (len(cells) - 1)
    canvas = Image.new("RGB", (W, 560), (255, 255, 255))
    x = 0
    for c in cells:
        canvas.paste(c, (x, 0))
        x += c.width + 15
    canvas.save(OUT / f"{cid}_候选网格.png")


def main() -> None:
    for cid, queries in ROLES.items():
        hits: list[dict] = []
        for q in queries:
            hits += search(q)
        order = pick(hits)
        paths = []
        for i, h in enumerate(order[:4], 1):
            out = CAND / f"{cid}_p{i}.jpg"
            if not out.exists():
                subprocess.run(["curl", "-sL", "-m", "40", "-o", str(out), h["largeImageURL"]], check=False)
            if out.exists():
                paths.append(out)
        grid(cid, paths)
        print(f"✓ {cid}: {len(paths)} 候选", flush=True)
    print(f"\n✓ 全部完成 → {OUT}")


if __name__ == "__main__":
    main()
