"""T18 快测：真人音色 + 拎电池动作 — 480p × 5s

核心验证：sample_west_male_v2（真人老外男 15s）在 H3 克隆后的自然度
用法: .venv/Scripts/python.exe tools/test_t18_battery.py [--dry]
输出: out/tests/t18_battery_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action fun commercial in vertical framing, natural daylight inside a small wheelchair repair shop. One single continuous shot, 5 seconds, no cuts. The camera pushes in. Man B (S2), a 22-year-old foreign young man with deep golden wavy hair and an oatmeal knit sweater (matching the SECOND reference image), looks the small wheelchair up and down, nods, then frowns a little and says at a natural, brisk conversational pace: <d>[Chinese] 新的是挺好，就是充电费劲吧？</d> — Man A (S1), a 70-year-old foreign stylish man with neat white hair, trimmed white beard and dark blue suit (matching the FIRST reference image), reaches down, picks the small black battery box up off the silver-grey lightweight wheelchair with ONE hand (the wheelchair matches the THIRD, FOURTH and FIFTH reference images: silver-grey frame, black seat, red springs, brand lettering), holds the box up at chest height and gives it a little shake twice, casual and confident, and says: <d>[Chinese] 电池拎回屋充，插上就完事了。</d> In the corner stands a big old battered electric wheelchair, clearly old and junk. Only these two men speak in this shot, taking turns one right after the other with no overlap; the speaker's mouth moves only while he speaks. Exactly two people and exactly two clearly different wheelchairs in the frame; no extra people. No on-screen text or subtitles; no watermarks.

overall_soundscape: Small repair shop ambience, a soft clink of tools, the light rattle of the battery box being shaken, plus clear natural indoor voices.

non_diegetic_music: N/A

Hard constraints: no text anywhere in frame; the battery box is small and held with ONE hand, the same box; the small wheelchair keeps its red springs and brand lettering; no background music."""

REF_IMAGES = [
    "assets/cast/library/fashion_western_grandpa.png",
    "assets/cast/library/fashion_western_boy_22.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/sample_west_male_v2.mp3",
    "assets/cast/voice/sample_young_male_v2.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t18_battery_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T18 快测（真人音色首发）| 5s | 480p竖", flush=True)
    if dry:
        print("  (dry) keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
