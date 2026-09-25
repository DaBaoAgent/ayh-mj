"""城市角色扩充：10 个（家庭关系+职业+年龄段全覆盖）+ 音色定妆用介绍词

新增方向（与已有12城市角色互补）：
  奶奶/外婆/女婿/儿媳/5岁孙女/保安/外卖骑手/女教师/退休教授/运动青年
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
STYLE = ("Photorealistic documentary portrait, ordinary-looking Chinese, no beauty filter, no "
         "makeup look, visible skin texture, vertical composition, no text, no logo, no watermark. ")

# (id, 图提示词, 音色定妆介绍词[3-5s])
CAST_CITY_EXT = [
    ("city_grandma_70",
     "a 70-year-old Chinese woman, short silver permed hair, wearing a purple knit cardigan and a "
     "small pearl necklace, warm gentle smile, " + CITY_BG,
     "我是城里的奶奶，今年七十啦。"),
    ("city_grandma_maternal_65",
     "a 65-year-old Chinese woman, round kindly face, hair in a neat bun, wearing a dark blue "
     "traditional button-up jacket, soft mild expression, " + CITY_BG,
     "外婆给你炖了汤，趁热喝。"),
    ("city_son_in_law_38",
     "a 38-year-old Chinese man, neat short hair, wearing a light blue dress shirt tucked into "
     "casual slacks, polite refined look like a dependable son-in-law, " + CITY_BG,
     "爸，这事交给我，您放心。"),
    ("city_daughter_in_law_32",
     "a 32-year-old Chinese woman, soft shoulder-length hair, wearing a cream knit sweater and a "
     "simple apron, gentle capable expression, " + CITY_BG,
     "妈，试试这个，可轻了。"),
    ("city_toddler_girl_5",
     "a 5-year-old Chinese little girl, two tiny pigtails, wearing a kindergarten uniform and a "
     "tiny backpack, cheerful adorable smile, " + CITY_BG,
     "爷爷，我们去公园玩吧！"),
    ("city_security_guard_45",
     "a 45-year-old Chinese man security guard, short flat hair, wearing a dark blue uniform with "
     "a cap under one arm, honest humble face, " + CITY_BG,
     "您好，这边登记一下。"),
    ("city_delivery_rider_28",
     "a 28-year-old Chinese man food delivery rider, wearing a yellow delivery jacket, holding a "
     "helmet under his arm, slightly sweaty face, friendly rushed look, " + CITY_BG,
     "您好，您的快递到了！"),
    ("city_teacher_woman_42",
     "a 42-year-old Chinese woman school teacher, thin-framed glasses, hair in a low ponytail, "
     "wearing a beige trench coat, intellectual gentle aura, " + CITY_BG,
     "同学们，方法比答案重要。"),
    ("city_retired_professor_70",
     "a 70-year-old Chinese man retired professor, grey hair combed back, wearing a wool vest over "
     "a checked shirt and glasses, scholarly calm demeanor, " + CITY_BG,
     "慢一点，稳一点，就对了。"),
    ("city_athlete_man_25",
     "a 25-year-old Chinese man athlete, short sporty hair with a thin headband, wearing athletic "
     "jacket over a wicking shirt, sunny energetic face, " + CITY_BG,
     "早起跑五公里，一天都精神。"),
]

if __name__ == "__main__":
    todo = [(cid, desc) for cid, desc, _ in CAST_CITY_EXT if not (OUT / f"{cid}.png").exists()]
    print(f"城市角色扩充: 10 个，本次需生成 {len(todo)} 个", flush=True)
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
