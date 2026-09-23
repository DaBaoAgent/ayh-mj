"""全身版定妆图（full 变体）— 解决构图不达标问题

根因：H3 会模仿参考图的构图——原定妆图是半身肖像（medium close-up），
生成镜头也跟着半身/近景，达不到"大全景+人物占画面1/2"。
修法：用全身版定妆图（人物完整全身+占画面高度约1/2+环境可见+嘴唇闭合）。

产出到 assets/cast/emotions/{son,mother,elder}_full.png
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
         "ultra-realistic skin texture, natural autumn daylight in a Chinese residential community "
         "with blurred green trees and buildings, shot on Canon EOS R5 35mm wide lens, "
         "FULL-BODY WIDE SHOT vertical composition")

FULL_CLAUSE = ("EXTREME WIDE SHOT, camera FAR AWAY (about 8-10 meters distance): the person is "
               "standing far from the camera and appears SMALL in the frame; the COMPLETE figure "
               "from head to toe is clearly visible with generous empty space above the head and "
               "below the feet, ground pavement extending in front of the person; the person "
               "occupies only about HALF of the frame height in the middle of a wide open plaza "
               "with lots of surrounding environment (buildings, trees, ground) all around. "
               "Lips are COMPLETELY CLOSED, mouth shut tight, calm neutral expression, not talking. ")

JOBS = [
    {
        "name": "son_full.png",
        "ref": CAST / "son_portrait.png",
        "prompt": (f"{STYLE}. The same 45-year-old Chinese man as in the reference image: black "
                   f"jacket, grey shirt, blue jeans, black short hair, stubble. {FULL_CLAUSE}"
                   "Same face, same hairstyle, same clothing as the reference image."),
    },
    {
        "name": "mother_full.png",
        "ref": CAST / "mother_portrait.png",
        "prompt": (f"{STYLE}. The same 68-year-old Chinese woman as in the reference image: "
                   f"plum-red fleece jacket, grey-black short hair. {FULL_CLAUSE}"
                   "Same face, same hairstyle, same clothing as the reference image."),
    },
    {
        "name": "elder_full.png",
        "ref": CAST / "elder_portrait.png",
        "prompt": (f"{STYLE}. The same 65-year-old Chinese man as in the reference image: "
                   f"grey-white short hair, dark navy jacket. {FULL_CLAUSE}"
                   "Same face, same hairstyle, same clothing as the reference image."),
    },
]

if __name__ == "__main__":
    ok, fail = 0, 0
    for job in JOBS:
        out = OUT / job["name"]
        if out.exists():
            print(f"↻ {job['name']} 已存在，跳过", flush=True)
            ok += 1
            continue
        print(f"🎨 生成 {job['name']}（参考: {job['ref'].name}）...", flush=True)
        try:
            result = gen_image(job["prompt"], str(out), aspect="3:4", quality="high",
                               ref_images=[str(job["ref"])])
            print(f"  ✓ {job['name']} ({result['bytes'] / 1024:.0f}KB)", flush=True)
            ok += 1
        except Exception as e:
            print(f"  ✗ {job['name']} 失败: {str(e)[:150]}", flush=True)
            fail += 1
    print(f"\n完成: {ok} 成功, {fail} 失败")
