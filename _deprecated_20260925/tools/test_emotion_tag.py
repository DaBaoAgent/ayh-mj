"""T18 音质实验：情绪标注写法测试 — 480p × 5s

目的：验证 H3 是否支持「（情绪副词）」标注（写在 <d> 台词内、文本前）。
对照基线 = T17 正式片镜1（无标注版）。
判定：①转写若出现"得意地/不服气地"= H3 把标注念出来了 → 不可行
      ②转写无标注词但语气有变化 = 可行 → 正式采用
用法: .venv/Scripts/python.exe tools/test_emotion_tag.py [--dry]
输出: out/tests/emotion_tag_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short comedy-drama in vertical framing, natural daylight in a park lane. One single continuous shot, 5 seconds, no cuts. A WIDE shot: TWO wheelchairs stay clearly visible side by side in the SAME frame — the small silver-grey lightweight electric wheelchair with Man A on the LEFT, the big bulky old wheelchair with Man B on the RIGHT; broken glass and small pebbles lie scattered on the lane ahead. Man B (S2), a 55-year-old foreign stylish man with silver-white combed-back hair, deep purple suit (matching the SECOND reference image), pats his big wheelchair, proud and smug, and says: <d>[Chinese]（得意地）我这台可是进口的，稳赢你。</d> — Man A (S1), a 70-year-old foreign stylish man with neat white hair and trimmed white beard, dark blue suit (matching the FIRST reference image), answers calmly: <d>[Chinese]（不服气地）比一把不就知道了嘛。</d> Only these two men speak in this shot, taking turns one right after the other with no overlap; the speaker's mouth moves only while he speaks. Exactly two people and exactly two clearly different wheelchairs in the frame; the wheelchairs never swap riders. No on-screen text or subtitles; no watermarks.

overall_soundscape: Park ambience, light birds, soft electric motor hums, clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/library/fashion_western_grandpa.png",
    "assets/cast/library/fashion_western_gent_55.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_grandpa_70.mp3",
    "assets/cast/voice/western_dad_45.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "emotion_tag_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 情绪标注实验 | 5s | 480p竖", flush=True)
    if dry:
        print("  (dry) keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 实验片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
