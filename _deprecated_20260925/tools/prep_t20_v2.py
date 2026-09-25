"""T20 v2 修复 — 镜1 儿子脸特写→快拉全景 + 说话人绑定强化 + 音色年龄感

修复根因：r12/r03 样本基频太近（234/235Hz）→ H3 区分度低
修复手段：①让儿子先入镜（锚定音色）②每句 ONLY (Sx) 嘴动 ③音色描述加年龄/音高特征
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

REFS = [
    ROOT / "assets/cast/elder_portrait.png",
    LIB / "core_son_38.png",
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]
AUDIOS = [VOICE / "r12_elder_male.mp3", VOICE / "r03_young_male.mp3"]

PROMPT = (
    "integrated_multimodal_description: Live-action fun commercial in vertical framing. "
    "Pacing is tight and bouncy; everyone speaks at a natural, brisk conversational pace. The first line starts "
    "within the first quarter second, every line begins immediately after the previous line's last word and "
    "immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a "
    "second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is "
    "always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Shot like "
    "real documentary footage: natural available light with soft realistic shadows, lifelike skin texture with "
    "visible pores and fine lines, natural hair detail, true-to-life colors, shallow depth of field like an 85mm "
    "lens at f/2, photorealistic and candid — no plastic skin, no over-smoothing.\n\n"
    "CAST (STRICTLY BIND — exactly two people and exactly ONE wheelchair; each person appears EXACTLY ONCE per "
    "shot, never duplicated; no extra bystanders): both Chinese, speaking standard Mandarin.\n"
    "- Man A (S1): a 75-year-old grandpa with white hair and deep wrinkles, grey knit sweater, exactly as in the "
    "FIRST reference image — the grandpa. VOICE (S1): an ELDERLY man's voice — low, deep, slow and unhurried "
    "(reference audio 1).\n"
    "- Man B (S2): a 38-year-old man with neat short hair and a light blue shirt, sweaty and out of breath, "
    "exactly as in the SECOND reference image — the son. VOICE (S2): a YOUNG man's voice — lighter, quicker, "
    "higher-pitched and breathless (reference audio 2). The two voices are clearly DIFFERENT in pitch and age; "
    "never swap them.\n"
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching the THIRD, FOURTH and FIFTH "
    "reference images: silver-grey frame, black cushion seat, red springs, brand lettering as in references). "
    "The SAME single wheelchair in every shot.\n\n"
    "[Shot 1, 0 to 4 seconds] The shot OPENS on Man B (S2)'s sweaty, panting face in EXTREME CLOSE-UP filling the "
    "frame — he wipes his forehead, and as he starts speaking the camera pulls back FAST to a wide shot of the "
    "mountain trail, revealing Man A (S1) sitting relaxed on the wheelchair a few steps ahead. Man B (S2) leans on "
    "his knees and says, out of breath, while his face is on screen: <d>[Chinese] 爸，咱歇会儿吧，我真走不动了！</d> "
    "— Man A (S1) waves him on casually: <d>[Chinese] 这才走一半呢。</d> ONLY (S2)'s mouth moves when (S2) speaks; "
    "when (S1) answers, ONLY (S1)'s mouth moves and (S2)'s lips stay closed. Only these two speak in this shot, "
    "taking turns with no overlap.\n\n"
    "[Shot 2, 4 to 8 seconds] Hard cut, closer on the two: Man B (S2) eyes the gentle slope ahead and says "
    "skeptically: <d>[Chinese] 您这车能上这个坡？</d> — Man A (S1) smirks, taps the armrest: "
    "<d>[Chinese] 说句话就行。</d> ONLY (S2)'s mouth moves for his line; ONLY (S1)'s mouth moves for his. Only "
    "these two speak.\n\n"
    "[Shot 3, 8 to 11 seconds] Hard cut: Man A (S1) speaks toward the wheelchair casually: "
    "<d>[Chinese] 往上走。</d> — the wheelchair immediately rolls forward up the slope on its own, steady and "
    "smooth, nobody touching it; Man B (S2) stumbles after it, reaching out, shouting: <d>[Chinese] 等等我！</d> "
    "ONLY (S1)'s mouth moves for his line; ONLY (S2)'s mouth moves for his. Only these two speak.\n\n"
    "[Shot 4, 11 to 14.5 seconds] Hard cut to the summit viewpoint, golden sunset: Man A (S1) sits on the "
    "wheelchair at the top, calm and smug; Man B (S2) arrives far below, doubled over, gasping, lips closed. Man A "
    "(S1) pats the armrest and says to camera, finishing right before the video ends: "
    "<d>[Chinese] 它比儿子听话，爱优护轻便侠。</d> ONLY (S1) speaks in this final shot.\n\n"
    "Only one person speaks at a time in this order — (S2) then (S1) in shot 1; (S2) then (S1) in shot 2; (S1) "
    "then (S2) in shot 3; (S1) in shot 4. All dialogue spoken verbatim, no overlap, no extra words, no omissions, "
    "no repeated lines. No on-screen text; dialogue is audio only.\n\n"
    "overall_soundscape: Mountain trail ambience, birdsong, soft wind, footsteps on stone, the quiet electric hum "
    "of the wheelchair climbing, plus clear natural voices.\n\n"
    "non_diegetic_music: N/A\n\n"
    "Hard constraints: render no watermarks, subtitles or text anywhere; exactly ONE wheelchair, always the small "
    "silver-grey lightweight one; the wheelchair moves on its own ONLY in shot 3, nobody touches it while moving; "
    "the two men never swap clothes, faces, voices or roles; the elder's voice stays deep and elderly and the "
    "young man's voice stays lighter and younger in EVERY line; no extra people; no background music; looks stay "
    "exactly consistent with the reference images; hard cuts only, no fades."
)


def main() -> None:
    out = {
        "job_uid": "job_manual_T20_v2",
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
    jp = ROOT / "state/onetake_prompt_job_manual_T20_v2.json"
    jp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs/onetake_check_T20_v2.txt").write_text(PROMPT, encoding="utf-8")
    print(f"✓ v2 spec: {jp}")


if __name__ == "__main__":
    main()
