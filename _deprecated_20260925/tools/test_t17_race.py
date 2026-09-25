"""T17 快测：两车竞速 + 大车趴窝（最难画面） — 480p × 5s

用法: .venv/Scripts/python.exe tools/test_t17_race.py [--dry]
输出: out/tests/t17_race2_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short comedy-drama in vertical framing, natural daylight in a park lane. One single continuous shot, 5 seconds, no cuts. A WIDE shot: BOTH wheelchairs stay clearly visible side by side in the SAME frame the whole time, racing forward together along the park lane — the small silver-grey lightweight wheelchair with Man A on the LEFT, the big bulky old wheelchair with Man B on the RIGHT; broken glass and small pebbles are clearly scattered on the lane ahead of them, glinting in the sunlight. Two wheelchairs race forward along the park lane: WHEELCHAIR A, the small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH and SIXTH reference images: silver-grey metal frame, black seat, red shock-absorbing springs, brand lettering; an electric wheelchair, never manual) with Man A (S1) — a 70-year-old foreign stylish man with neat white hair, trimmed white beard, dark blue suit (matching the FIRST reference image) — riding and staying perfectly calm; and WHEELCHAIR B, a big heavy old-school electric wheelchair with silver-grey tube frame and wide black seat (matching the SEVENTH reference image) with Man B (S2) — a 55-year-old foreign stylish man with silver-white combed-back hair, deep purple suit (matching the SECOND reference image) — riding. Small pieces of broken glass and scattered pebbles lie on the lane. Suddenly the big bulky wheelchair B wobbles and stalls — its tires go flat, the wheelchair tilts slightly and stops; Man B (S2) looks down in panic at his wheels and cries: <d>[Chinese] 哎等会儿！我这轮子咋回事？！</d> — meanwhile the small silver-grey wheelchair A rolls steadily right over the broken glass and pebbles without the slightest wobble; Man A (S1) stays calm and says: <d>[Chinese] 实心胎，扎不动。</d> Woman C (S3) — a 20-year-old foreign cool girl with black bob hair and silver leather jacket (matching the THIRD reference image) — stands at the roadside watching with wide eyes. Only these two men speak in this shot, taking turns one right after the other with no overlap; the speaker's mouth moves only while he speaks. Exactly three people and exactly two clearly different wheelchairs in the frame; nobody else; the wheelchairs never swap riders, merge or change into each other. No on-screen text or subtitles; no watermarks.

overall_soundscape: Park ambience, light birds, soft electric motor hums; a brief deflating hiss and wobble when the big wheelchair stalls; clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: no text anywhere in frame; the big wheelchair only stalls and wobbles — it never tips over or crashes; the small wheelchair never loses a wheel and rolls over the glass smoothly; no background music."""

REF_IMAGES = [
    "assets/cast/library/fashion_western_grandpa.png",
    "assets/cast/library/fashion_western_gent_55.png",
    "assets/cast/library/fashion_western_girl_20.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_grandpa_70.mp3",
    "assets/cast/voice/western_dad_45.mp3",
    "assets/cast/voice/western_young_woman_28.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t17_race2_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T17 快测 | 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t17_race_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
