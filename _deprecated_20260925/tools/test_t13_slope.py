"""T13 快测：7 图方案 + 两车绑定 + 爬坡失败画面 — 480p × 5s

验证点（本片三大新变量）：
  1. 7 张参考图能否正常跑（首次）
  2. 两台车/两个人绑定不混（老王=轻便侠、老张=普通大轮椅）
  3. "冲坡失败+往后溜"画面能否画出来

用法: .venv/Scripts/python.exe tools/test_t13_slope.py [--dry]
输出: out/tests/t13_slope_test.mp4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight at a residential compound entrance with a noticeable uphill ramp. One single continuous shot, 5 seconds, no cuts. Exactly two men and exactly two clearly different wheelchairs in the whole frame. Man A (S1) is a 75-year-old Chinese man with white hair and deep wrinkles in a grey sweater (matching the SECOND reference image); he ALWAYS stays with the BIG ORDINARY wheelchair (matching the SEVENTH reference image: a large heavy traditional electric wheelchair with silver-grey tube frame and wide black seat). Man B (S2) is a 70-year-old Chinese man with grey-white combed-back hair in dark blue work clothes (matching the FIRST reference image); he stands calmly beside his small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH and SIXTH reference images: silver-grey metal frame, black seat, red shock-absorbing springs, brand lettering as in the reference images; an electric wheelchair, never a bicycle or manual wheelchair). The two wheelchairs never swap owners, merge or turn into each other; each person appears exactly once; no extra bystanders. Man A (S1) waves dismissively at the small wheelchair, climbs into his big wheelchair and says at a slightly brisk pace: <d>[Chinese] 便宜货能行吗？我先上！</d> — then he drives it at the ramp; the big wheelchair labors halfway up, the wheels slip, it stalls and slides backwards down a short way, wobbling badly; he grips the armrests with both hands, panicking, and cries out: <d>[Chinese] 哎哎哎！咋还往下溜呢！</d> The camera pushes in with a light handheld sway, keeping both men and both wheelchairs in frame. Only Man A speaks in this shot; his mouth moves only while he speaks; Man B keeps his mouth closed. The big wheelchair never tips over or crashes — it only stalls and slides back a short way. No on-screen text or subtitles; no watermarks.

overall_soundscape: Quiet residential ambience, the strained whining motor of the big wheelchair struggling and slipping on the ramp, brief tire-scuffing as it slides back, plus clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: the two wheelchairs must never swap owners, merge or turn into each other; the big wheelchair never tips over or crashes; no text anywhere in frame; no background music."""

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
    out = ROOT / "out" / "tests" / "t13_slope_test.mp4"
    payload = {"prompt": PROMPT, "duration": 5, "resolution": "480p竖"}
    for i, img in enumerate(REF_IMAGES):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    for i, a in enumerate(REF_AUDIOS):
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(ROOT / a), resize=False)

    print(f"🧪 T13 快测：7图+两车绑定+爬坡失败 | 5s | 480p竖 | 参考图 {len(REF_IMAGES)} + 音频 {len(REF_AUDIOS)}", flush=True)
    if dry:
        print("  (dry) payload keys:", list(payload.keys()), flush=True)
        return

    tid = ac.create_task(WF, payload)
    print(f"  ✓ task_id: {tid}", flush=True)
    (ROOT / "out/tests/t13_slope_task.json").write_text(
        json.dumps({"task_id": tid, "workflow": WF}, ensure_ascii=False, indent=1), encoding="utf-8")
    url = ac.poll_task(tid, interval=20)
    ac.download(url, str(out))
    print(f"✓ 快测片: {out}", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
