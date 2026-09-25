"""生成 10 个代表角色的「照片级」版角色图 + 与原图对比拼图

对比目标：AI 生成（原图） vs 照片级真实感（新图）
输出：assets/cast/library_real/<id>.png（新图）
      assets/cast/compare/<id>_对比.png（左原图/右新图）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ARK = ROOT / "s4_generate/ark_image.py"
PY = ROOT / ".venv/Scripts/python.exe"
LIB = ROOT / "assets/cast/library"
OUT = ROOT / "assets/cast/library_real"
CMP = ROOT / "assets/cast/compare"
OUT.mkdir(parents=True, exist_ok=True)
CMP.mkdir(parents=True, exist_ok=True)

TMPL = ("Photorealistic professional portrait photograph of {desc}, half-body shot facing the camera, real candid "
        "photography style, shot on 85mm lens, shallow depth of field, blurred neutral background, natural soft "
        "lighting, ultra-realistic skin texture, fine facial details, no text, no watermark")

CHARS = [
    ("city_grandpa_75", "a 75-year-old Chinese grandpa with white hair and deep wrinkles, wearing a grey knit sweater, kind but stubborn expression"),
    ("city_grandma_70", "a 70-year-old Chinese grandma with silver curled hair, wearing a purple cardigan and a pearl necklace, kind warm smile"),
    ("city_mom_45", "a 45-year-old Chinese woman with shoulder-length hair, wearing a beige cardigan, gentle warm but slightly tired expression"),
    ("city_young_man_30", "a 30-year-old Chinese man with short black hair, wearing a green workwear jacket, friendly easy smile"),
    ("fashion_granny_silver", "a 68-year-old elegant Chinese grandma with big silver wavy hair, sunglasses on top of head, beige trench coat, chic and confident"),
    ("fashion_girl_20", "a 20-year-old cool Chinese girl with black short hair with highlights, wearing an oversized black suit, confident street style"),
    ("western_grandpa_70", "a 70-year-old western grandpa with neat white hair, blue eyes, beige cardigan and round glasses, kindly scholarly"),
    ("western_young_woman_28", "a 28-year-old western young woman with a blonde ponytail, wearing a cream white sweater, bright and curious"),
    ("city_boy_10", "a 10-year-old Chinese boy with a buzz cut, wearing red and white sportswear, lively happy smile"),
    ("fashion_gent_55", "a 55-year-old distinguished Chinese gentleman with silver-grey slicked-back hair, wearing a dark green suit, elegant and refined"),
]


def gen(desc: str, out: Path) -> bool:
    prompt = TMPL.format(desc=desc)
    r = subprocess.run([str(PY), str(ARK), "--prompt", prompt, "--aspect", "3:4", "-o", str(out)],
                       capture_output=True, text=True)
    return out.exists()


def make_compare(cid: str) -> bool:
    a, b = LIB / f"{cid}.png", OUT / f"{cid}.png"
    if not (a.exists() and b.exists()):
        return False
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    h = 640
    ia = ia.resize((int(ia.width * h / ia.height), h))
    ib = ib.resize((int(ib.width * h / ib.height), h))
    canvas = Image.new("RGB", (ia.width + ib.width + 20, h), (255, 255, 255))
    canvas.paste(ia, (0, 0))
    canvas.paste(ib, (ia.width + 20, 0))
    canvas.save(CMP / f"{cid}_对比.png")
    return True


def main() -> None:
    ok = 0
    for cid, desc in CHARS:
        out = OUT / f"{cid}.png"
        if not out.exists():
            print(f"⚙ 生成 {cid} ...", flush=True)
            if not gen(desc, out):
                print(f"  ✗ {cid} 失败", flush=True)
                continue
        if make_compare(cid):
            ok += 1
            print(f"  ✓ {cid} 对比图完成", flush=True)
    print(f"\n✓ {ok}/10 角色图 + 对比图完成\n  新图: {OUT}\n  对比: {CMP}")


if __name__ == "__main__":
    main()
