"""EP001-SC001 v3 表情增强版逐镜生成（含新旧轮椅视觉设定）

设定（老板修正 2026-09-23）：
  · 母亲坐在**破旧旧轮椅**上（磨损/锈迹/破座垫）——镜1/2/4
  · 儿子手上的是**爱优护新轮椅**（轻便侠218 折叠状态）——镜3
链路：情绪定妆图 + 面部强化提示词 + 逐镜独立生成 → 拼接
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.tools import ffmpeg
from s4_generate.autodl_client import generate_video

ROOT = Path(__file__).resolve().parent.parent
CAST = ROOT / "assets" / "cast"
EMO = CAST / "emotions"
PRODUCT = ROOT / "assets" / "products"
OUT = ROOT / "out" / "story_v3_emotion"

# 参考图
REF_SON_URGENT = str(EMO / "son_urgent.png")
REF_MOTHER_STUBBORN = str(EMO / "mother_stubborn.png")
REF_MOTHER_SOFT = str(EMO / "mother_softening.png")
REF_OLD = str(CAST / "old_wheelchair.png")
REF_FOLD = str(PRODUCT / "折叠-无阴影.png")
REF_SIDE = str(PRODUCT / "正侧-3-无阴影.png")

HARD = ("Hard constraints: render no watermarks, subtitles, captions, floating text, letters, "
        "numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; "
        "keep the product's own brand lettering exactly as it appears in the reference image; "
        "no background music; everyone keeps complete visual consistency with the reference images.")

OLD_DESC = ("an OLD WORN-OUT electric wheelchair with scratched faded grey frame, rust spots, "
            "torn black seat cushion with tape patches and a loose dangling brake cable")

SHOTS = [
    {
        "seq": 1, "duration": 3,
        "refs": [REF_SON_URGENT, REF_MOTHER_STUBBORN, REF_OLD],
        "prompt": (
            "integrated_multimodal_description: [Shot 1] Live-action documentary drama, urgent "
            "handheld camera feel. Autumn afternoon in a Chinese residential community: grey paving "
            "tiles, blurred green trees, soft dappled sunlight. A 45-year-old Chinese man (S1) in a "
            "black jacket and blue jeans suddenly grips the armrest of " + OLD_DESC + " where a "
            "68-year-old Chinese woman (S2) in a plum-red fleece is sitting; the camera tilts up to "
            "his tense face, eyebrows drawn together deep, mouth open mid-shout; he leans forward "
            "and shouts urgently at a natural, fast pace: <d>[Chinese] 妈！刹车都松了，你还敢骑？</d> "
            "The woman glares up at him with tightened lips, not speaking, mouth closed. Both keep "
            "their exact faces, hairstyles and clothing from the reference images; the wheelchair "
            "keeps its exact worn-out look from the reference image. Only the man speaks; nobody "
            "else moves their mouth.\n\n"
            "overall_soundscape: Outdoor community ambience, a metallic rattle of the loose brake "
            "cable, quick footsteps, distant birds; the man's voice is sharp and urgent.\n\n"
            "non_diegetic_music: N/A\n\n" + HARD),
    },
    {
        "seq": 2, "duration": 4,
        "refs": [REF_MOTHER_STUBBORN, REF_OLD],
        "prompt": (
            "integrated_multimodal_description: [Shot 2] Live-action documentary drama, static "
            "medium close-up with shallow depth of field. Autumn afternoon in a Chinese residential "
            "community, blurred green trees behind. A 68-year-old Chinese woman (S2) in a plum-red "
            "fleece zip jacket sits in " + OLD_DESC + "; her face fills the frame, brows deeply "
            "furrowed, chin raised, lips pressed tight in stubborn defiance. She turns her head away "
            "and says stubbornly at a measured, firm pace: <d>[Chinese] 我骑十年了，轮不到你说扔就扔。</d> "
            "Her lips stay closed after finishing; the man beside her stays out of focus and silent, "
            "mouth closed. She keeps her exact face, hairstyle and clothing from the reference image; "
            "the wheelchair keeps its exact worn-out look. Only the woman speaks.\n\n"
            "overall_soundscape: Quiet community ambience with birds and distant traffic; her voice "
            "is low and firm.\n\n"
            "non_diegetic_music: N/A\n\n" + HARD),
    },
    {
        "seq": 3, "duration": 4,
        "refs": [REF_SON_URGENT, REF_FOLD, REF_SIDE],
        "prompt": (
            "integrated_multimodal_description: [Shot 3] Live-action documentary drama, low angle "
            "medium shot, camera slowly pushes in for a premium feel. Autumn afternoon at a car "
            "trunk in a Chinese residential community, grey paving tiles. A 45-year-old Chinese man "
            "(S1) in a black jacket lifts the folded frame of a BRAND-NEW silver-grey lightweight "
            "electric wheelchair with ONE hand, fresh clean paint and intact seat, and slides it "
            "smoothly into the car trunk, then says proudly at a natural, brisk pace: <d>[Chinese] "
            "这个才十三点八公斤，一只手拎得动。</d> His lips stay closed after finishing. The new "
            "wheelchair frame keeps its exact folded shape, color and brand lettering from the "
            "reference images as it moves. Nobody else is in frame. Only the man speaks.\n\n"
            "overall_soundscape: Outdoor ambience with a soft click as the frame folds and a smooth "
            "slide sound as it enters the trunk; his voice is clear and confident.\n\n"
            "non_diegetic_music: N/A\n\n" + HARD),
    },
    {
        "seq": 4, "duration": 4,
        "refs": [REF_MOTHER_SOFT, REF_OLD],
        "prompt": (
            "integrated_multimodal_description: [Shot 4] Live-action documentary drama, static "
            "close-up on a face with shallow depth of field. Autumn afternoon in a Chinese "
            "residential community. A 68-year-old Chinese woman (S2) in a plum-red fleece sits in "
            + OLD_DESC + ", looking toward a car trunk off screen, her expression softening with "
            "doubt, brow relaxing; she asks softly, half-doubting at a natural pace: <d>[Chinese] "
            "真的假的？</d> Then her lips close and relax, and she gives a tiny nod. A 45-year-old "
            "man's voice continues from off screen, warm and light, while everyone in frame keeps "
            "their lips completely closed: <d>[Chinese] 你试试，折叠，塞后备箱。</d> She keeps her "
            "exact face, hairstyle and clothing from the reference image; the old wheelchair keeps "
            "its exact worn-out look. Nobody in frame moves their mouth while the off-screen voice "
            "speaks.\n\n"
            "overall_soundscape: Gentle breeze and distant birds; her voice is soft, the off-screen "
            "voice is warm and close.\n\n"
            "non_diegetic_music: N/A\n\n" + HARD),
    },
]


def gen_shot(shot: dict) -> dict:
    seq = shot["seq"]
    out_path = OUT / "shots" / f"shot_{seq:02d}.mp4"
    if out_path.exists() and out_path.stat().st_size > 100 * 1024:
        return {"seq": seq, "status": "cached", "path": str(out_path)}

    result = generate_video(
        prompt=shot["prompt"],
        ref_images=shot["refs"],
        duration=shot["duration"],
        resolution="768p竖",
        out_path=str(out_path),
        workflow="minimax_h3_lightx2v_v5",
    )
    return {"seq": seq, "status": "ok", **result}


def main() -> int:
    (OUT / "shots").mkdir(parents=True, exist_ok=True)

    # 参考图存在性检查
    for shot in SHOTS:
        for ref in shot["refs"]:
            if not Path(ref).exists():
                print(f"✗ 参考图缺失: {ref}", flush=True)
                return 1

    print("🎬 表情增强版：4镜快切（情绪定妆+旧新轮椅设定+全程对白）", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(gen_shot, s): s for s in SHOTS}
        for future in as_completed(futures):
            shot = futures[future]
            try:
                r = future.result()
                results.append(r)
                print(f"  ✓ 镜{r['seq']}: {r['status']} {r.get('cost', 0)}元", flush=True)
            except Exception as e:
                print(f"  ✗ 镜{shot['seq']} 失败: {str(e)[:120]}", flush=True)
                results.append({"seq": shot["seq"], "status": "failed", "error": str(e)[:200]})

    results.sort(key=lambda x: x["seq"])
    ok = [r for r in results if r["status"] in ("ok", "cached")]
    print(f"\n完成 {len(ok)}/{len(SHOTS)}", flush=True)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    if len(ok) < len(SHOTS):
        print("⚠ 有镜头失败，等重跑补齐后再拼接", flush=True)
        return 1

    # 拼接
    concat_list = OUT / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file 'shots/shot_{s['seq']:02d}.mp4'" for s in SHOTS),
        encoding="utf-8")
    final = OUT / "final_15s_emotion.mp4"
    cmd = [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
           "-c", "copy", str(final.name)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(OUT))
    if r.returncode != 0:
        print("流拷贝失败，改用重编码拼接...", flush=True)
        cmd = [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
               "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
               "-c:a", "aac", "-b:a", "128k", str(final.name)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(OUT))
        if r.returncode != 0:
            print("拼接失败:", r.stderr[-500:], flush=True)
            return 1

    print(f"✓ 成片: {final}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
