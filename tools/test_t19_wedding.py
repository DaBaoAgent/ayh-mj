"""T19 快测：婚礼+车自动前进+真人音色 — 480p × 5s

核心验证：r12/r05 真人音色克隆效果 + 车"自己动了" + 婚礼现场元素
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIB = ROOT / "assets/cast/library"
PROD = ROOT / "assets/products"
VOICE = ROOT / "assets/cast/voice/real"

REFS = [LIB / "fashion_grandpa_2.png", LIB / "fashion_girl_20.png",
        PROD / "折叠-无阴影.png", PROD / "正侧-3-无阴影.png", PROD / "45度-加水杯-无阴影.png"]
AUDIOS = [VOICE / "r12_elder_male.mp3", VOICE / "r05_young_female.mp3"]

PROMPT = (
    "integrated_multimodal_description: Live-action fun commercial in vertical framing, natural warm daylight at a "
    "wedding-venue entrance with a flower arch and a red carpet, blurred guests behind. A single 5-second shot, "
    "camera swaying slightly. CAST (STRICTLY BIND — exactly two people, one wheelchair):\n"
    "- Man A (S1): a 75-year-old elegant grandpa, neat white hair, round-brim hat, camel overcoat, sitting on the "
    "wheelchair, exactly as in the FIRST reference image.\n"
    "- Girl (S2): a 20-year-old cool girl, black short hair with highlights, oversized black suit, exactly as in the "
    "SECOND reference image.\n"
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching the THIRD, FOURTH and FIFTH "
    "reference images), the same one throughout.\n\n"
    "The wheelchair rolls forward smoothly about half a meter on its own, slowly, nobody touching it; Girl (S2) "
    "stares wide-eyed, pointing at the wheelchair, and shouts in delight: <d>[Chinese] 它真听您的？！</d> — Man A "
    "(S1) sits up proudly, chin up, smug little smile, and says: <d>[Chinese] 说走就走，比谁都听话。</d> Voice "
    "binding: (S1) same voice as reference audio 1, (S2) same voice as reference audio 2. The first line starts "
    "within a quarter second; no pause exceeds a third of a second. Only one person speaks at a time, (S2) then "
    "(S1). No omissions, no repeated lines. Nobody else in frame.\n\n"
    "overall_soundscape: Wedding venue ambience, distant happy chatter, quiet electric hum of the wheelchair.\n\n"
    "non_diegetic_music: N/A\n\n"
    "Hard constraints: no watermarks or text; one wheelchair only; nobody touches the wheelchair while it moves; "
    "faces and clothes stay exactly consistent with the reference images."
)


def main() -> None:
    out = {
        "job_uid": "job_test_T19",
        "template_id": "manual", "template_name": "manual", "mode": "manual",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": [],
        "duration": 5,
        "resolution": "480p竖",
        "ref_images": [str(p) for p in REFS],
        "ref_audios": [str(p) for p in AUDIOS],
        "prompt": PROMPT,
        "lines_meta": [],
    }
    jp = ROOT / "state/onetake_prompt_job_manual_T19_test.json"
    jp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ 快测 spec: {jp}")


if __name__ == "__main__":
    main()
