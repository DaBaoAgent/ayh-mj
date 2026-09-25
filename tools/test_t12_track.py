"""T12 快测：跟拍运镜 + 轮椅无人自走 — 480p × 5s

验证点（此前从未跑过的新变量）：
  1. 侧向跟拍（tracking）运镜是否成立、画面是否稳定
  2. 轮椅"无人自走"是否画对（不被画成人推 / 人不碰车）
  3. 台词逐字 + 镜内双人轮次

用法: .venv/Scripts/python.exe tools/test_t12_track.py [--dry]
输出: out/tests/t12_track_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight on a suburban house driveway with green lawn. One single continuous shot, 5 seconds, no cuts. The camera moves sideways in one smooth tracking move alongside an unfolded silver-grey electric wheelchair, keeping it centered as the wheelchair drives across the driveway entirely on its own — nobody pushes it and nobody sits on it; its four small wheels roll on the ground and its red shock springs and brand lettering are visible. A 40-year-old Caucasian woman matching the FIRST reference image (auburn curly hair, grey turtleneck) stands on the driveway watching it come, her eyes wide; a 45-year-old Caucasian man matching the SECOND reference image (brown hair with grey at the temples, army-green jacket) stands beside her with a small remote control in one hand, calm and pleased. The man (S2) says first, calmly proud, at a slightly brisk pace: <d>[Chinese] 咱按一下，它自己就过来。</d> — and immediately, right after his last word, the woman (S1) blurts out in disbelief: <d>[Chinese] 哎哟喂，它真过来了！</d> Only these two people speak in this shot, taking turns one right after the other with no overlap and no pause longer than a beat; the man's mouth moves only while (S2) speaks, and the woman's mouth moves only while (S1) speaks. Exactly two people in the whole frame, each appears exactly once — never duplicate, clone, mirror or twin any person anywhere in the frame; no extra bystanders. The wheelchair must exactly match the THIRD, FOURTH and FIFTH reference images: silver-grey metal frame, black seat, four wheels, red shock-absorbing springs, brand lettering as in the reference images; it is an electric wheelchair with a motor in its rear wheels, never a plain manual wheelchair, never a bicycle or scooter; it is never touched or pushed by anyone while it moves. No on-screen text or subtitles; no watermarks. The people's full bodies from head to toe are visible.

overall_soundscape: Quiet suburban ambience, light birdsong, one small remote-control click, and the soft rolling hum of the wheelchair's small wheels on concrete, plus clear natural voices outdoors.

non_diegetic_music: N/A

Hard constraints: the wheelchair must never turn into a plain manual wheelchair, bicycle, scooter or motorcycle, and must never be pushed or touched by anyone while moving; keep the brand lettering as in the reference images; no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/library/western_mom_40.png",
    "assets/cast/library/western_dad_45.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_mom_40.mp3",
    "assets/cast/voice/western_dad_45.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t12_track_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T12 快测：跟拍运镜+自走车 | 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t12_track_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
