"""T20《爬山打脸》准备 — 新规范 v2 全特性首秀（2026-09-25）

组合：核心卡司 × voice_ai（语音播报）× B11 景点打卡 × G4 脑洞广告
新特性：钩子（冲突喊话）/0.5s冲击开场/双反转/光线质感词统一
音色：老王=r12_elder_male（真人）/ 儿子=r03_young_male（真人）
剧情：爬山中儿子跟不上 → 老王说句话车就上山 → "它比儿子听话"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.prompt_parts import REALISM, PACE, COLD_OPEN

LIB = ROOT / "assets/cast/library"
PROD = ROOT / "assets/products"
VOICE = ROOT / "assets/cast/voice/real"

REFS = [
    ROOT / "assets/cast/elder_portrait.png",
    LIB / "core_son_38.png",
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]
AUDIOS = [VOICE / "r12_elder_male.mp3", VOICE / "r03_young_male.mp3"]

PROMPT = (
    "integrated_multimodal_description: Live-action fun commercial in vertical framing. " + PACE + " " + REALISM + " "
    + COLD_OPEN + "\n\n"
    "CAST (STRICTLY BIND — exactly two people and exactly ONE wheelchair; each person appears EXACTLY ONCE per shot, "
    "never duplicated; no extra bystanders): both Chinese, speaking standard Mandarin.\n"
    "- Man A (S1): a 75-year-old grandpa with white hair and deep wrinkles, grey knit sweater, exactly as in the "
    "FIRST reference image — the grandpa.\n"
    "- Man B (S2): a 38-year-old man with neat short hair and a clean shirt, slightly sweaty and out of breath, "
    "exactly as in the SECOND reference image — the son.\n"
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching the THIRD, FOURTH and FIFTH "
    "reference images: silver-grey frame, black cushion seat, red springs, brand lettering as in references). "
    "The SAME single wheelchair in every shot.\n\n"
    "[Shot 1, 0 to 4 seconds] A scenic mountain trail with a gentle stone-paved slope in warm afternoon light: Man B (S2) leans on "
    "his knees, panting heavily and wiping sweat, and says: <d>[Chinese] 爸，咱歇会儿吧，我真走不动了！</d> — Man A "
    "(S1) sits relaxed on the wheelchair, waving him on: <d>[Chinese] 这才走一半呢。</d> Only these two speak, "
    "taking turns with no overlap.\n\n"
    "[Shot 2, 4 to 8 seconds] Hard cut, closer: Man B (S2) eyes the steep slope ahead and says skeptically: "
    "<d>[Chinese] 您这车能上这个坡？</d> — Man A (S1) smirks, taps the armrest: <d>[Chinese] 说句话就行。</d> "
    "Only these two speak.\n\n"
    "[Shot 3, 8 to 11 seconds] Hard cut: Man A (S1) speaks toward the wheelchair casually: <d>[Chinese] 往上走。</d> "
    "— the wheelchair immediately rolls forward up the slope on its own, steady and smooth, nobody touching it; Man "
    "B (S2) stumbles after it, reaching out, shouting: <d>[Chinese] 等等我！</d> Only these two speak.\n\n"
    "[Shot 4, 11 to 14.5 seconds] Hard cut to the summit viewpoint, golden sunset: Man A (S1) sits on the wheelchair "
    "at the top, calm and smug; Man B (S2) arrives far below, doubled over, gasping. Man A (S1) pats the armrest and "
    "says to camera, finishing right before the video ends: <d>[Chinese] 它比儿子听话，爱优护轻便侠。</d> Only Man A "
    "speaks in this final shot; Man B stays silent, lips closed.\n\n"
    "Only one person speaks at a time in this order — (S2) then (S1) in shot 1; (S2) then (S1) in shot 2; (S1) then "
    "(S2) in shot 3; (S1) in shot 4. Voice binding: (S1) same voice as reference audio 1, (S2) same voice as "
    "reference audio 2. All dialogue spoken verbatim, no overlap, no extra words, no omissions, no repeated lines. "
    "No on-screen text; dialogue is audio only.\n\n"
    "overall_soundscape: Mountain trail ambience, birdsong, soft wind, footsteps on stone, the quiet electric hum "
    "of the wheelchair climbing, plus clear natural voices.\n\n"
    "non_diegetic_music: N/A\n\n"
    "Hard constraints: render no watermarks, subtitles or text anywhere; exactly ONE wheelchair, always the small "
    "silver-grey lightweight one; the wheelchair moves on its own ONLY in shot 3, nobody touches it while moving; "
    "the two men never swap clothes, faces or roles; no extra people; no background music; looks stay exactly "
    "consistent with the reference images; hard cuts only, no fades."
)


def main() -> None:
    out = {
        "job_uid": "job_manual_T20",
        "template_id": "manual", "template_name": "manual", "mode": "manual",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": [],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": [str(p) for p in REFS],
        "ref_audios": [str(p) for p in AUDIOS],
        "prompt": PROMPT,
        "lines_meta": [],
    }
    jp = ROOT / "state/onetake_prompt_job_manual_T20.json"
    jp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs/onetake_check_T20.txt").write_text(PROMPT, encoding="utf-8")
    print(f"✓ spec: {jp}")
    for p in REFS + AUDIOS:
        assert p.exists(), f"缺: {p}"
    print(f"✓ 参考图 {len(REFS)} + 音频 {len(AUDIOS)} 就位")


if __name__ == "__main__":
    main()
