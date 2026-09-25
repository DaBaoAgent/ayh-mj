"""生成 ayh-mj 人物定妆图（真实感版，参考真实人物参考图风格）

产出目录：assets/cast/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from s4_generate.ark_image import gen_image

OUT = Path(__file__).resolve().parent.parent / "assets" / "cast"
OUT.mkdir(parents=True, exist_ok=True)

# 通用风格词（无美颜无滤镜真实感）
STYLE = ("Photorealistic documentary photography, candid unretouched photo, "
         "no beauty filter, no makeup, no retouching, ordinary everyday Chinese person, "
         "ultra-realistic skin texture with visible pores and natural imperfections, "
         "natural daylight with soft shadows, shot on Canon EOS R5 85mm lens, "
         "autumn in a Chinese residential community with grey paving tiles and blurred green trees")

MOTHER = ("A 68-year-old Chinese woman with short grey-black hair, round weathered face, "
          "deep natural wrinkles on forehead and around eyes, age spots, slightly sagging cheeks, "
          "calm tired eyes. Wearing a plum-red fleece zip-up jacket")

MOTHER_FULL = (MOTHER + ", black loose cotton pants, light pink slip-on shoes. "
               "She sits on a silver-grey lightweight electric wheelchair with a black seat, "
               "hands resting naturally on the armrests, feet on the footrest")

SON = ("A 45-year-old Chinese man with short black slightly messy hair, square face, "
       "tan skin, light stubble, faint frown lines, calm but concerned expression. "
       "Wearing an open black casual jacket over a dark grey t-shirt, blue straight jeans")

JOBS = [
    ("mother_portrait.png",
     f"{STYLE}. {MOTHER}, looking at the camera. Medium close-up portrait, waist-up. "
     f"Vertical composition"),
    ("mother_wheelchair.png",
     f"{STYLE}. {MOTHER_FULL}. Full body shot showing her seated on the wheelchair. "
     f"Vertical composition"),
    ("son_portrait.png",
     f"{STYLE}. {SON}, standing, looking at the camera. Medium close-up portrait, waist-up. "
     f"Vertical composition"),
]

if __name__ == "__main__":
    for name, prompt in JOBS:
        out = OUT / name
        if out.exists():
            print(f"↻ {name} 已存在，跳过", flush=True)
            continue
        print(f"🎨 生成 {name}...", flush=True)
        try:
            result = gen_image(prompt, str(out), aspect="3:4", quality="high")
            print(f"  ✓ {name} ({result['bytes'] / 1024:.0f}KB)", flush=True)
        except Exception as e:
            print(f"  ✗ {name} 失败: {str(e)[:150]}", flush=True)
