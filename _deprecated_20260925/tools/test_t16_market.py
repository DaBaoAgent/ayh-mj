"""T16 快测：时尚组新角色 + 购物袋挂满车 + 借音色 — 480p × 5s

用法: .venv/Scripts/python.exe tools/test_t16_market.py [--dry]
输出: out/tests/t16_market_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight at the entrance of a supermarket. One single continuous shot, 5 seconds, no cuts. The camera sweeps sideways. A small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH and SIXTH reference images: silver-grey metal frame, black seat with thick cushion, red shock-absorbing springs, brand lettering; an electric wheelchair, never manual) stands loaded like a pack mule — five or six full plastic grocery bags hang on its push handles and backrest, bulging with groceries, nobody sits in it. Woman A (S1), a 68-year-old Chinese stylish woman with silvery wavy hair, sunglasses pushed up on her head, beige trench coat, red lipstick (matching the FIRST reference image), ties one last bag onto the handle and pats the ballooning bags, satisfied. Woman B (S2), a 24-year-old Chinese stylish girl with two-tone highlighted hair and a black leather biker jacket (matching the SECOND reference image), walks past, stops and stares at the mountain of bags, amazed, and says: <d>[Chinese] 奶奶，您这是把超市搬回家啊？</d> — Woman A (S1) turns her head proudly and answers at a slightly brisk pace: <d>[Chinese] 打折呢，一车全装下。</d> Man C (S3), a 27-year-old fresh-looking Chinese man in a light blue shirt over a white tee (matching the THIRD reference image), stands at the side watching with wide curious eyes. Only these two women speak in this shot, taking turns one right after the other with no overlap; the speaker's mouth moves only while she speaks. Each person appears exactly once; no extra people; the wheelchair is never duplicated; the bags never fall. No on-screen text or subtitles; no watermarks.

overall_soundscape: Supermarket entrance ambience, distant shopping carts, soft plastic-bag rustle, clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: no text anywhere in frame; the wheelchair keeps its thick black seat cushion and red springs exactly as in the reference images; grocery bags hang all over the wheelchair; nobody sits in the wheelchair; no background music."""

REF_IMAGES = [
    "assets/cast/library/fashion_granny_silver.png",
    "assets/cast/library/fashion_girl_street.png",
    "assets/cast/library/fashion_boy_fresh.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/city_grandma_70.mp3",
    "assets/cast/voice/city_young_woman_26.mp3",
    "assets/cast/voice/city_young_man_30.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t16_market_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T16 快测 | 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t16_market_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
