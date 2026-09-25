"""T11 快测：镜内双句来回（S1→S2 同镜先后说话）— 480p × 5s

验证点（此前从未跑过的新变量）：
  1. 同一镜内两人先后说话（来-回），台词逐字
  2. 口型归属切换：S1 说时只有 S1 嘴动、S2 说时只有 S2 嘴动
  3. 双音色归属正确（女声→大妈、男声→教授）

用法: .venv/Scripts/python.exe tools/test_t11_shot1.py [--dry]
输出: out/tests/t11_shot1_test.mp4 + task id 落盘 out/tests/t11_shot1_task.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight in front of an old residential building entrance. One single continuous shot, 5 seconds, no cuts. A 55-year-old Chinese woman in purple sportswear with a grocery basket on her arm, matching the FIRST reference image, walks up to a silver-grey electric wheelchair that stands folded and upright on the ground like a compact vertical column, leans in and looks it up and down with a sour, nosy smirk; a 70-year-old Chinese man in a wool vest and glasses, matching the SECOND reference image, stands beside the wheelchair, one hand resting on its handlebar, calm and smiling. The woman (S1) says in a sour, teasing tone at a slightly brisk pace: <d>[Chinese] 哟，教授，您这又换新车啦？</d> — and immediately, right after her last word, the man (S2) answers in a calm, easy tone: <d>[Chinese] 轻便的，可好使了。</d> Only these two people speak in this shot, taking turns one right after the other with no overlap, no pause longer than a beat; the woman's mouth moves only while (S1) speaks, and the man's mouth moves only while (S2) speaks. Exactly two people in the whole frame, each appears exactly once — never duplicate, clone, mirror or twin any person anywhere in the frame; no extra bystanders. The wheelchair must exactly match the THIRD, FOURTH and FIFTH reference images: silver-grey metal frame, black seat, four wheels, red shock-absorbing springs, brand lettering as in the reference images; it is an electric wheelchair, never a plain manual wheelchair, never a bicycle or scooter; it stays folded and upright on the ground, never laid flat on its side. No on-screen text or subtitles; no watermarks. Camera: low wide shot, both people's full bodies from head to toe visible.

overall_soundscape: Quiet residential compound ambience, light breeze, a soft grocery-basket rattle, clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: the wheelchair must never turn into a plain manual wheelchair, bicycle, scooter or motorcycle; keep the brand lettering as in the reference images; no text anywhere in frame; no background music."""

REF_IMAGES = [
    "assets/cast/library/city_neighbor_aunt_55.png",
    "assets/cast/library/city_retired_professor_70.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/city_neighbor_aunt_55.mp3",
    "assets/cast/voice/city_retired_professor_70.mp3",
]


def main(dry: bool = False) -> None:
    out = ROOT / "out" / "tests" / "t11_shot1_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T11 快测：镜内双句 | 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t11_shot1_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
