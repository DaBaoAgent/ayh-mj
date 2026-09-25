"""T14 快测：3 音色（首次）+ 单手提起 + 老外魔性 — 480p × 5s

验证点：①3 条 ref_audio 是否稳定 ②"单手提车离地"能否画出 ③4 老外脸一致性
用法: .venv/Scripts/python.exe tools/test_t14_light.py [--dry]
输出: out/tests/t14_light_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action fun commercial in vertical framing, natural daylight at the entrance of a residential compound. One single continuous shot, 5 seconds, no cuts. Comical, exaggerated performances — big wide eyes, raised eyebrows. Three foreigners who speak Chinese and exactly ONE small silver-grey LIGHTWEIGHT electric wheelchair (matching the FIFTH, SIXTH and SEVENTH reference images: silver-grey metal frame, black seat, red shock-absorbing springs, its own brand lettering; an electric wheelchair, never manual). Woman B (S2), a 40-year-old foreign woman with red-brown curly hair and green eyes, grey turtleneck (matching the SECOND reference image), walks around the wheelchair, sizing it up curiously, and asks: <d>[Chinese] 这么小个儿，得有三十公斤吧？</d> — immediately Man A (S1), a 70-year-old foreign man with white hair and blue eyes in a beige cardigan and glasses (matching the FIRST reference image), steps in, grasps the wheelchair frame with ONE hand and lifts the whole wheelchair up off the ground, holding it effortlessly at his side like it weighs nothing, and says: <d>[Chinese] 十三点八公斤。</d> — and Man C (S3), a 30-year-old foreign man with sandy-blond hair in a dark-blue pilot jacket (matching the THIRD reference image), leans in, doubtful, and asks: <d>[Chinese] 真的假的？我单手试试！</d> The camera pushes in slightly with a light sway. Only these three speak, strictly one after another with no overlap; the speaker's mouth moves only while he speaks. Each person appears exactly once; no extra people; nobody sits in the wheelchair; the wheelchair is never duplicated. The wheelchair is lifted with one hand and looks clearly light. No on-screen text or subtitles; no watermarks.

overall_soundscape: Quiet residential ambience, a soft light metallic touch as the wheelchair is lifted, plus clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: the wheelchair is lifted up off the ground with ONE hand and looks clearly light; no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/library/western_grandpa_70.png",
    "assets/cast/library/western_mom_40.png",
    "assets/cast/library/western_young_man_30.png",
    "assets/cast/library/western_dad_45.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_grandpa_70.mp3",
    "assets/cast/voice/western_mom_40.mp3",
    "assets/cast/voice/western_young_man_30.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t14_light_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T14 快测 | 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}（3音色首次）", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t14_light_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
