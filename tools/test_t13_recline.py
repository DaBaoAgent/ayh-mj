"""T13 快测（后躺版）：靠背放平+当场躺下 — 480p × 5s

验证点：轻便侠"145度后躺"形态变化能否画出（形态变化类动作 H3 有经验：折叠/展开）
用法: .venv/Scripts/python.exe tools/test_t13_recline.py [--dry]
输出: out/tests/t13_recline_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight at a residential compound entrance. One single continuous shot, 5 seconds, no cuts. A 70-year-old Chinese man with grey-white combed-back hair in dark blue work clothes (matching the FIRST reference image) sits in a small silver-grey LIGHTWEIGHT electric wheelchair (matching the THIRD, FOURTH and FIFTH reference images: silver-grey metal frame, black seat, red shock-absorbing springs, brand lettering) and presses a button on the armrest — the backrest smoothly reclines backwards until he lies back comfortably at a wide angle, hands relaxed on his chest, eyes closing in comfort; the red shock springs and brand lettering stay visible. A 75-year-old Chinese man with white hair and deep wrinkles in a grey sweater (matching the SECOND reference image) stands beside his BIG ORDINARY wheelchair (matching the SEVENTH reference image) and stares, dumbfounded; a 70-year-old Chinese woman with silver curly hair in a purple cardigan (matching the SIXTH reference image) watches with wide eyes. The reclining man (S2) says, relaxed: <d>[Chinese] 中午困了，我躺会儿。</d> — and immediately the standing man (S1) blurts out in disbelief: <d>[Chinese] 哎哟喂！还能躺平？！</d> The camera pushes in slightly and tilts down a little, following the reclining backrest. Only these two speak, taking turns one right after the other with no overlap; the reclining man's mouth moves while he speaks even though he is lying back. Exactly three people and exactly two clearly different wheelchairs in the frame; no extra people; the wheelchairs never swap owners. The backrest reclines smoothly all the way to a wide lying angle; the wheelchair stays stable and never tips over. No on-screen text or subtitles; no watermarks.

overall_soundscape: Quiet residential ambience, one soft mechanical whirr as the backrest reclines smoothly, plus clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: the backrest reclines smoothly to a wide lying angle and the man lies back comfortably; the wheelchair stays stable and never tips over; no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/elder_portrait.png",
    "assets/cast/library/city_grandpa_75.png",
    "assets/cast/library/city_grandma_70.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/elder_voice.mp3",
    "assets/cast/voice/city_grandpa_75.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t13_recline_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T13 快测（后躺版）| 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t13_recline_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
