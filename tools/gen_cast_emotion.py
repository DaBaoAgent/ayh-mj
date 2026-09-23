"""表情定妆图变体：愤怒/急切/倔强/松动（用基础定妆图做参考保持人物一致）

产出到 assets/cast/emotions/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from s4_generate.ark_image import gen_image

ROOT = Path(__file__).resolve().parent.parent
CAST = ROOT / "assets" / "cast"
OUT = CAST / "emotions"
OUT.mkdir(parents=True, exist_ok=True)

STYLE = ("Photorealistic documentary photography, candid unretouched photo, no beauty filter, "
         "no retouching, ultra-realistic skin texture with visible pores, natural autumn daylight "
         "in a Chinese residential community with blurred green trees, shot on Canon EOS R5 85mm, "
         "medium close-up portrait, vertical composition")

JOBS = [
    {
        "name": "son_urgent.png",
        "ref": CAST / "son_portrait.png",
        "prompt": (f"{STYLE}. The same 45-year-old Chinese man as in the reference image, black "
                   "jacket, blue jeans. His face is tense with urgency and worry: eyebrows drawn "
                   "together deep, eyes wide and anxious, mouth open mid-shout as if calling out "
                   "to someone, slight forward lean of the head. Same hairstyle, same face as the "
                   "reference image."),
    },
    {
        "name": "mother_stubborn.png",
        "ref": CAST / "mother_portrait.png",
        "prompt": (f"{STYLE}. The same 68-year-old Chinese woman as in the reference image, "
                   "plum-red fleece jacket. Her face is stubborn and defiant: brows deeply "
                   "furrowed, eyes glaring slightly upward, chin raised, lips pressed tight with a "
                   "downward stubborn turn, mouth closed. Same grey-black short hair, same face as "
                   "the reference image."),
    },
    {
        "name": "mother_softening.png",
        "ref": CAST / "mother_portrait.png",
        "prompt": (f"{STYLE}. The same 68-year-old Chinese woman as in the reference image, "
                   "plum-red fleece jacket. Her expression is softening with doubt and curiosity: "
                   "brow slightly relaxed from a frown, eyes soft and hesitating, lips just "
                   "slightly parted as if asking a half-believing question, the corner of her "
                   "mouth lifting just a little. Same grey-black short hair, same face as the "
                   "reference image."),
    },
]

if __name__ == "__main__":
    for job in JOBS:
        out = OUT / job["name"]
        if out.exists():
            print(f"↻ {job['name']} 已存在，跳过", flush=True)
            continue
        print(f"🎨 生成 {job['name']}（参考: {job['ref'].name}）...", flush=True)
        try:
            result = gen_image(job["prompt"], str(out), aspect="3:4", quality="high",
                               ref_images=[str(job["ref"])])
            print(f"  ✓ {job['name']} ({result['bytes'] / 1024:.0f}KB)", flush=True)
        except Exception as e:
            print(f"  ✗ {job['name']} 失败: {str(e)[:150]}", flush=True)
