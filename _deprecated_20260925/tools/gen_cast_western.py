"""欧美角色扩充：5 个（说中文的外国人）— 图 + 音色定妆词

用途：外籍邻居/跨国家庭/外籍朋友场景；音色=外国人带口音说中文
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate.ark_image import gen_image

OUT = ROOT / "assets" / "cast" / "library"

CITY_BG = ("standing in a Chinese city residential community, grey paving tiles, blurred modern "
           "apartment buildings and green trees, autumn afternoon light")
STYLE = ("Photorealistic documentary portrait, ordinary-looking Western Caucasian, no beauty "
         "filter, no makeup look, visible skin texture, vertical composition, no text, no logo, "
         "no watermark. ")

# (id, 图提示词, 音色定妆词[中文], 音色描述)
CAST_WESTERN = [
    ("western_grandpa_70",
     "a 70-year-old Western Caucasian man, short white hair, light blue eyes, deep smile lines, "
     "wearing a beige knit cardigan over a checked shirt and thin glasses, kind scholarly "
     "expression, " + CITY_BG,
     "我在这儿住了十年，中国话没问题。",
     "a warm, slightly hoarse elderly foreign man speaking Chinese with a light accent"),
    ("western_dad_45",
     "a 45-year-old Western Caucasian man, short brown hair with grey at the temples, stubble, "
     "wearing a dark olive field jacket over a grey tee, easygoing dependable look, " + CITY_BG,
     "我太太是中国人，我妈也说中文。",
     "a clear, friendly middle-aged foreign man speaking Chinese with a light accent"),
    ("western_mom_40",
     "a 40-year-old Western Caucasian woman, shoulder-length wavy auburn hair, green eyes, "
     "wearing a soft grey turtleneck and simple necklace, warm capable expression, " + CITY_BG,
     "轻便得很，我一只手就能提。",
     "a soft, clear adult foreign woman speaking Chinese with a light accent"),
    ("western_young_woman_28",
     "a 28-year-old Western Caucasian woman, long blonde hair in a low ponytail, wearing a "
     "cream cable-knit sweater and jeans, bright curious expression, " + CITY_BG,
     "这个设计，比我想的聪明多了。",
     "a bright, lively young foreign woman speaking Chinese with a light accent"),
    ("western_young_man_30",
     "a 30-year-old Western Caucasian man, short sandy hair, light beard, wearing a navy bomber "
     "jacket over a white tee, relaxed friendly smile, " + CITY_BG,
     "试试这个，真挺轻的。",
     "a bright young foreign man speaking Chinese with a light accent"),
]

if __name__ == "__main__":
    todo = [(cid, desc) for cid, desc, _, _ in CAST_WESTERN if not (OUT / f"{cid}.png").exists()]
    print(f"欧美角色: 5 个，本次需生成 {len(todo)} 个", flush=True)
    failed = []
    for i, (cid, desc) in enumerate(todo, 1):
        try:
            print(f"[{i}/{len(todo)}] {cid}...", flush=True)
            gen_image(prompt=STYLE + desc, out_path=str(OUT / f"{cid}.png"))
            print(f"  ✓ {cid}", flush=True)
        except Exception as e:
            failed.append(cid)
            print(f"  ✗ {cid}: {str(e)[:120]}", flush=True)
    print(f"\n完成: {len(todo) - len(failed)}/{len(todo)}", flush=True)
    if failed:
        raise SystemExit(1)
