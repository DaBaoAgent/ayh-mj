"""闭嘴版定妆图（quiet 变体）— 解决非说话人动嘴问题

根因：H3 会把参考图的表情带到非说话人脸上——原定妆图/情绪图嘴部微张或张开，
非说话人也会跟着动嘴。修法：非说话人一律用"嘴唇完全闭合"的 quiet 版参考图。

产出到 assets/cast/emotions/{son,mother,elder}_quiet.png
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
        "name": "son_quiet.png",
        "ref": CAST / "son_portrait.png",
        "prompt": (f"{STYLE}. The same 45-year-old Chinese man as in the reference image, black "
                   "jacket, blue jeans. His lips are COMPLETELY CLOSED and firmly sealed, mouth "
                   "shut tight with not a single tooth visible, calm neutral expression, quietly "
                   "watching and listening, no talking, no speaking, no open mouth. Same hairstyle, "
                   "same face, same lighting as the reference image."),
    },
    {
        "name": "mother_quiet.png",
        "ref": CAST / "mother_portrait.png",
        "prompt": (f"{STYLE}. The same 68-year-old Chinese woman as in the reference image, "
                   "plum-red fleece jacket. Her lips are COMPLETELY CLOSED and firmly sealed, "
                   "mouth shut tight with not a single tooth visible, calm neutral expression, "
                   "quietly listening, no talking, no speaking, no open mouth. Same grey-black "
                   "short hair, same face, same lighting as the reference image."),
    },
    {
        "name": "elder_quiet.png",
        "ref": CAST / "elder_portrait.png",
        "prompt": (f"{STYLE}. The same 65-year-old Chinese man as in the reference image, "
                   "grey-white short hair, dark navy jacket. His lips are COMPLETELY CLOSED and "
                   "firmly sealed, mouth shut tight with not a single tooth visible, calm neutral "
                   "expression, quietly watching, no talking, no speaking, no open mouth. Same "
                   "hairstyle, same face, same lighting as the reference image."),
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
