"""第1镜出片：15秒母子对白（H3 原生对白+口型+现场音效）

工作流：minimax_h3_lightx2v_v5_15s（15秒多图）
参考图：母亲定妆图 + 儿子定妆图 + 产品白底图
提示词：官方三段式（integrated_multimodal_description / overall_soundscape / non_diegetic_music）
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from s4_generate.autodl_client import generate_video

ROOT = Path(__file__).resolve().parent.parent

PROMPT = (
    "integrated_multimodal_description: [Shot 1] Live-action documentary style, one continuous "
    "steady shot. Autumn afternoon in a Chinese residential community, grey paving tiles, blurred "
    "green trees, soft dappled sunlight. A 45-year-old Chinese man (S1) in a black jacket and blue "
    "jeans kneels beside a silver-grey lightweight electric wheelchair with red front springs; a "
    "68-year-old Chinese woman (S2) in a plum-red fleece jacket sits in the wheelchair. Both faces "
    "stay unobstructed in a medium two-shot and keep their exact faces, hairstyles and clothing from "
    "the reference images. The man (S1) says with concern: <d>[Chinese] 妈，这车刹不住了，不能再骑。</d> "
    "The woman (S2) replies stubbornly: <d>[Chinese] 我用十年了，说扔就扔？</d> "
    "The man (S1) pats the folded frame: <d>[Chinese] 这个才十三点八公斤，一只手拎得动。</d> "
    "The woman (S2) mutters: <d>[Chinese] 花那冤枉钱干嘛。</d> "
    "The man (S1) unfolds it one-handed: <d>[Chinese] 你先试试，一键折叠，塞后备箱就走。</d> "
    "Speak at a natural, brisk conversational pace with no long pauses. Only one person speaks at a "
    "time in this exact order, verbatim: no overlap, no extra words, no omissions, no repetition, "
    "no interruption, no invented lines. The wheelchair keeps its exact frame shape, color and "
    "brand lettering from the reference image. Camera holds steady, no cuts.\n"
    "\n"
    "overall_soundscape: Quiet residential community ambience: a light breeze through trees, distant "
    "birds, faint footsteps on paving tiles, and a soft mechanical click when the wheelchair frame "
    "folds. Voices clear and natural outdoors.\n"
    "\n"
    "non_diegetic_music: N/A\n"
    "\n"
    "Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, "
    "stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the "
    "product's own brand lettering exactly as it appears in the reference image; no background "
    "music; both characters keep complete visual consistency with their reference images throughout."
)

REF_MOTHER = ROOT / "assets" / "cast" / "mother_portrait.png"
REF_SON = ROOT / "assets" / "cast" / "son_portrait.png"
REF_PRODUCT = ROOT / "assets" / "products" / "正侧-3-无阴影.png"

OUT_DIR = ROOT / "out" / "shot1_dialogue"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "shot1_15s_dialogue.mp4"
    if out_path.exists() and out_path.stat().st_size > 100 * 1024:
        print(f"↻ 已存在: {out_path}", flush=True)
        return 0

    # 提示词落盘（留档）
    (OUT_DIR / "prompt.txt").write_text(PROMPT, encoding="utf-8")

    print("🎬 第1镜出片：15秒母子对白（H3原生对白+口型）", flush=True)
    print(f"   参考图: {REF_MOTHER.name} + {REF_SON.name} + {REF_PRODUCT.name}", flush=True)

    def on_status(status, data):
        if status not in ("SUBMITTING",):
            print(f"   [{time.strftime('%H:%M:%S')}] {status}", flush=True)

    t0 = time.time()
    result = generate_video(
        prompt=PROMPT,
        ref_images=[str(REF_MOTHER), str(REF_SON), str(REF_PRODUCT)],
        duration=15,
        resolution="768p竖",
        out_path=str(out_path),
        workflow="minimax_h3_lightx2v_v5_15s",
        on_status=on_status,
    )
    elapsed = time.time() - t0
    print(f"\n✓ 出片完成 {elapsed / 60:.1f}分钟", flush=True)
    print(json.dumps(result, ensure_ascii=False, indent=1), flush=True)

    (OUT_DIR / "result.json").write_text(
        json.dumps({**result, "elapsed_s": round(elapsed)}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
