"""演员库批量扩充：24 个角色（城市12 + 农村12）

覆盖：年龄段(7-78岁) × 性别 × 城乡 × 家庭关系，供脚本按需智能调用
风格统一：photorealistic documentary / no beauty filter / ordinary-looking
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate.ark_image import gen_image

OUT = ROOT / "assets" / "cast" / "library"
OUT.mkdir(parents=True, exist_ok=True)

CITY_BG = ("standing in a Chinese city residential community, grey paving tiles, blurred modern "
           "apartment buildings and green trees, autumn afternoon light")
RURAL_BG = ("standing in a Chinese rural village yard, grey brick farmhouse and corn cobs hanging "
            "on the wall behind, bare earth ground, soft afternoon sunlight")

STYLE = ("Photorealistic documentary portrait, ordinary-looking Chinese, no beauty filter, no "
         "makeup look, visible skin texture, vertical composition, no text, no logo, no watermark. ")

# (id, 描述提示词)
CAST_LIB = [
    # ── 城市线 12 ──
    ("city_grandpa_75", "a 75-year-old Chinese man, white short hair, deep wrinkles, wearing a dark grey wool sweater and black trousers, kind but stubborn face, " + CITY_BG),
    ("city_mom_45", "a 45-year-old Chinese woman, shoulder-length black hair with a few grey strands, wearing a beige knit cardigan, gentle tired expression, " + CITY_BG),
    ("city_daughter_35", "a 35-year-old Chinese woman, neat low ponytail, wearing a light blue shirt and dark slacks like an office worker after hours, warm capable expression, " + CITY_BG),
    ("city_son_teen_16", "a 16-year-old Chinese boy, short black hair, wearing a blue and white school uniform with a backpack strap on one shoulder, slightly shy expression, " + CITY_BG),
    ("city_girl_8", "an 8-year-old Chinese girl, twin braids with pink hair ties, wearing a yellow hoodie, big curious eyes, holding a small schoolbag, " + CITY_BG),
    ("city_boy_10", "a 10-year-old Chinese boy, short buzz-cut hair, wearing a red and white sporty jacket, lively grin, " + CITY_BG),
    ("city_nurse_28", "a 28-year-old Chinese woman community nurse, hair in a bun, wearing a light pink uniform jacket over white top, gentle professional smile, " + CITY_BG),
    ("city_neighbor_aunt_55", "a 55-year-old Chinese woman, short permed hair, wearing a purple zip-up sport jacket like a square-dance auntie, chatty curious face, " + CITY_BG),
    ("city_young_man_30", "a 30-year-old Chinese man, short hair, wearing a dark green delivery-company jacket and black pants, tired but friendly, " + CITY_BG),
    ("city_young_woman_26", "a 26-year-old Chinese woman, long dark hair, wearing a cream trench coat, fashionable but natural, soft confident expression, " + CITY_BG),
    ("city_couple_70", "an elderly Chinese couple in their 70s: a 72-year-old man in a grey zip jacket and a 70-year-old woman in a maroon cardigan, standing side by side, " + CITY_BG),
    ("city_dad_50", "a 50-year-old Chinese man, short greying hair, wearing a dark blue work jacket like a bus driver off shift, weathered kind face, " + CITY_BG),
    # ── 农村线 12 ──
    ("rural_grandpa_78", "a 78-year-old Chinese rural man, deeply tanned wrinkled face, thin white hair under a straw hat, wearing a faded blue Mao-style jacket with mud stains on the cuffs, " + RURAL_BG),
    ("rural_grandma_72", "a 72-year-old Chinese rural woman, grey hair pulled back under a floral headscarf, deep smile lines, wearing a dark floral cotton jacket with an apron, " + RURAL_BG),
    ("rural_dad_48", "a 48-year-old Chinese rural man, short messy hair, weathered tan face, wearing a dark green camouflage work jacket and rubber boots with dirt, " + RURAL_BG),
    ("rural_mom_45", "a 45-year-old Chinese rural woman, hair in a simple bun with a red rubber band, wearing a small-flowered cotton blouse and dark pants, strong kind face, " + RURAL_BG),
    ("rural_daughter_30", "a 30-year-old Chinese rural woman, long black braid, wearing a pink sweater and jeans, carrying a travel bag like returning from city work, hopeful expression, " + RURAL_BG),
    ("rural_son_33", "a 33-year-old Chinese rural man, short hair, dusty construction worker clothes, dark blue jacket over grey shirt, honest tired face, " + RURAL_BG),
    ("rural_teen_15", "a 15-year-old Chinese rural girl, short ponytail, wearing a faded red school jacket, carrying cloth schoolbag, shy bright eyes, " + RURAL_BG),
    ("rural_kid_7", "a 7-year-old Chinese rural boy, bowl-cut hair, wearing a slightly oversized blue jacket with a cartoon print, cheeks red from sun, " + RURAL_BG),
    ("rural_uncle_60", "a 60-year-old Chinese rural man, grey stubble, wearing a worn brown leather jacket and cloth shoes, holding a long bamboo pipe, sly smile, " + RURAL_BG),
    ("rural_aunt_58", "a 58-year-old Chinese rural woman, short grey hair, wearing a dark green jacket with a red cloth bag over shoulder, lively talkative face, " + RURAL_BG),
    ("rural_couple_75", "an elderly Chinese rural couple in their 70s: a 76-year-old man in a faded grey jacket and a 74-year-old woman in a black headscarf and dark jacket, standing side by side, " + RURAL_BG),
    ("rural_village_doctor_40", "a 40-year-old Chinese rural village doctor, glasses, wearing a white coat over a dark sweater, carrying a black medical bag, reliable expression, " + RURAL_BG),
]

if __name__ == "__main__":
    todo = [(cid, desc) for cid, desc in CAST_LIB if not (OUT / f"{cid}.png").exists()]
    print(f"演员库批量生成: {len(CAST_LIB)} 个角色，本次需生成 {len(todo)} 个", flush=True)
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
        print("失败: " + ", ".join(failed), flush=True)
        raise SystemExit(1)
