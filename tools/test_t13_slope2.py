"""T13 快测2（单变量）：坡 + 大车冲坡失败 —— 480p × 5s

快测1 失败点：坡道没画出来 + 车出现手推圈。
本测最小化配置（1 人 + 1 台大车 + 显眼坡道），只验证「坡上挣扎+往后溜」能否画出。
参考图仅 2 张（grandpa_75 + 普通电动轮椅）——排除多图干扰。

用法: .venv/Scripts/python.exe tools/test_t13_slope2.py [--dry]
输出: out/tests/t13_slope2_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight. One single continuous shot, 5 seconds, no cuts. A clearly visible steep uphill ramp rises across the middle of the frame — an ordinary residential compound access ramp with railings on the side. A 75-year-old Chinese man with white hair and deep wrinkles in a grey sweater (matching the FIRST reference image) climbs into a BIG ORDINARY electric wheelchair (matching the SECOND reference image: a large heavy traditional electric wheelchair with a silver-grey tube frame and wide black seat). He says at a slightly brisk pace: <d>[Chinese] 我先上！</d> — then the big wheelchair drives up the steep ramp; it labors halfway up the incline, its wheels slip on the slope, it stalls ON the sloping surface and slides backwards down a short way, wobbling; the whole wheelchair is clearly tilted by the incline, its front lifted and its rear lower, never on flat ground; he grips the armrests with both hands, panicking, and cries out: <d>[Chinese] 哎哎哎！咋还往下溜呢！</d> The camera pushes in from behind with a light handheld sway, keeping the man, the wheelchair and the sloping ramp all clearly in frame the whole time. Exactly one person and exactly one electric wheelchair in the frame — no hand rims on its wheels, no other people, no other wheelchairs. Only the man speaks; his mouth moves only while he speaks. The wheelchair never tips over or crashes — it only stalls and slides back a short way. No on-screen text or subtitles; no watermarks.

overall_soundscape: Quiet residential ambience, the strained whining motor of the wheelchair struggling and slipping on the slope, brief tire-scuffing as it slides back, plus the man's panicky voice.

non_diegetic_music: N/A

Hard constraints: the wheelchair is clearly ON the sloping ramp, tilted by the incline, never on flat ground; it has no hand rims and looks clearly electric (joystick controller visible); it never tips over or crashes; no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/library/city_grandpa_75.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/city_grandpa_75.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t13_slope2_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T13 快测2（单变量：坡+大车）| 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t13_slope2_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测2片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
