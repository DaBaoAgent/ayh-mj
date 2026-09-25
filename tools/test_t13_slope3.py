"""T13 快测3（卡半坡版）：坡向上+车卡半坡+人着急 — 480p × 5s

快测2 教训：「动态溜坡」H3 画不出来（画成平稳下坡）→ 降级为「上不去+卡半坡+慌张」
本测强化：坡的向上方向感（镜头在坡底仰看）+ 车明显倾斜 + 人慌张动作

用法: .venv/Scripts/python.exe tools/test_t13_slope3.py [--dry]
输出: out/tests/t13_slope3_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight. One single continuous shot, 5 seconds, no cuts. The camera stands at the BOTTOM of an uphill access ramp and looks UP toward the building entrance: the ramp clearly rises away from the camera, its bottom edge closest to the viewer, its top farther away and higher, with side railings — this upward slope is the main setting and stays clearly visible for the whole shot. A 75-year-old Chinese man with white hair and deep wrinkles in a grey sweater (matching the FIRST reference image) sits in a BIG ORDINARY electric wheelchair (matching the SECOND reference image: a large heavy traditional electric wheelchair with a silver-grey tube frame and wide black seat). He says at a slightly brisk pace: <d>[Chinese] 我先上！</d> — then the big wheelchair tries to climb the ramp but CANNOT make it: it stalls barely halfway up, stuck on the sloping surface, clearly tilted by the incline with its front lifted higher than its rear, unable to move forward; the man leans forward and grips the armrests in panic, rocking anxiously in his seat, and cries out in alarm: <d>[Chinese] 哎哎哎！咋还往下溜呢！</d> The big wheelchair stays stuck on the slope, helpless; the camera pushes in with a light handheld sway, keeping the man, the wheelchair and the rising ramp all clearly in frame the whole time. Exactly one person and exactly one electric wheelchair in the frame — no other people, no other wheelchairs. Only the man speaks; his mouth moves only while he speaks. The wheelchair never tips over or crashes. No on-screen text or subtitles; no watermarks.

overall_soundscape: Quiet residential ambience, the strained whining motor of the wheelchair struggling on the slope, plus the man's panicky voice.

non_diegetic_music: N/A

Hard constraints: the wheelchair is clearly stuck ON the sloping ramp, tilted by the incline, never on flat ground, never rolling down smoothly; it never tips over or crashes; no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/library/city_grandpa_75.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/city_grandpa_75.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t13_slope3_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T13 快测3（卡半坡版）| 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t13_slope3_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测3片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
