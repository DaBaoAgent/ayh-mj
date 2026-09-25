"""T19《婚礼喊一声》准备 v2 — 合规格式（integrated_multimodal_description）

组合：时尚组 × voice_ai（AI语音播报·零门槛）× B10 婚礼出席 × G4 脑洞广告
音色：S1=爷爷=r12_elder_male / S2=孙女=r05_young_female / S3=爸爸=r09_adult_male（全真人）
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
    LIB / "fashion_grandpa_2.png",
    LIB / "fashion_girl_20.png",
    LIB / "fashion_gent_55.png",
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]
AUDIOS = [VOICE / "r12_elder_male.mp3", VOICE / "r05_young_female.mp3", VOICE / "r09_adult_male.mp3"]

PACE = ("Pacing is tight and bouncy; everyone speaks at a natural, brisk conversational pace. "
        "The first line starts within the first quarter second, every line begins immediately after the previous "
        "line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause "
        "exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing "
        "silence. The camera is always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — "
        "never static. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it.")

PROMPT = (
    "integrated_multimodal_description: Live-action fun commercial in vertical framing, natural warm daylight at a "
    "wedding-venue entrance: a flower arch, a red carpet, blurred guests in the background. This 14.5-second video "
    "contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. " + PACE + "\n\n"
    "CAST (STRICTLY BIND — exactly three people and exactly ONE wheelchair in the whole video; each person appears "
    "EXACTLY ONCE per shot, never duplicated, cloned, mirrored, split or twinned; no extra bystanders): all three are "
    "Chinese and speak standard Mandarin.\n"
    "- Man A (S1): a 75-year-old elegant grandpa with neat white hair, a round-brim hat and a camel overcoat, sitting "
    "on the hero wheelchair, exactly as in the FIRST reference image — the grandpa.\n"
    "- Girl (S2): a 20-year-old cool street-style girl with black short hair with highlights and an oversized black "
    "suit, exactly as in the SECOND reference image — the granddaughter.\n"
    "- Man B (S3): a 55-year-old distinguished gentleman with silver-grey slicked-back hair and a dark green suit, "
    "exactly as in the THIRD reference image — the father.\n"
    "WHEELCHAIR (the hero's one): the small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH "
    "and SIXTH reference images: silver-grey metal frame, black seat with thick cushion, four wheels, red "
    "shock-absorbing springs, its own brand lettering exactly as in the reference images; an electric wheelchair, "
    "never manual). The SAME single wheelchair appears in every shot.\n\n"
    "[Shot 1, 0 to 4 seconds] The camera sweeps sideways at the venue entrance: Girl (S2) runs up to Man A (S1) "
    "and says, breathless and a bit wheedling: <d>[Chinese] 爷爷，婚礼马上开始了，快点！</d> — Man A (S1) frowns "
    "down at the wheelchair, worried, and says: <d>[Chinese] 这车，我还没学会呢。</d> Only these two speak in this "
    "shot, taking turns one right after the other with no overlap.\n\n"
    "[Shot 2, 4 to 8 seconds] Hard cut to a closer shot: Man B (S3) walks to Man A's side, bends down, pats his "
    "shoulder and says encouragingly: <d>[Chinese] 爸，您就说句话试试。</d> — Man A (S1) opens his mouth timidly, "
    "speaking quietly and hesitantly: <d>[Chinese] 往前……走？</d> Only these two speak in this shot, taking turns "
    "one right after the other with no overlap.\n\n"
    "[Shot 3, 8 to 11 seconds] Hard cut, the camera sways slightly: the wheelchair rolls forward smoothly about half "
    "a meter on its own; Girl (S2) stares wide-eyed, pointing at the wheelchair, and shouts in delight: "
    "<d>[Chinese] 它真听您的？！</d> — Man A (S1) sits up proudly, chin up, smug little smile, and says: "
    "<d>[Chinese] 说走就走，比谁都听话。</d> Only these two speak in this shot, taking turns one right after the "
    "other with no overlap.\n\n"
    "[Shot 4, 11 to 14.5 seconds] Hard cut, the camera pulls back into a wide shot: Man B (S3) laughs heartily and "
    "says, teasing: <d>[Chinese] 这伴郎，没白请。</d> — Man A (S1) tips his round-brim hat with one hand and smiles "
    "at the camera, finishing right before the video ends: <d>[Chinese] 爱优护轻便侠。</d> Only these two speak in "
    "this final shot, taking turns one right after the other with no overlap.\n\n"
    "Only one person speaks at a time in this exact order — (S2) then (S1) in shot 1; (S3) then (S1) in shot 2; "
    "(S2) then (S1) in shot 3; (S3) then (S1) in shot 4. Voice binding: (S1) speaks with the same voice as reference "
    "audio 1, (S2) the same voice as reference audio 2, (S3) the same voice as reference audio 3. All dialogue must "
    "be spoken verbatim, no overlap, no extra words, no omissions, no repeated lines, no interruptions, no invented "
    "lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as "
    "text.\n\n"
    "overall_soundscape: Wedding venue ambience, distant happy chatter of guests, a soft breeze, the quiet electric "
    "hum of the wheelchair rolling, plus clear natural voices.\n\n"
    "non_diegetic_music: N/A\n\n"
    "Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price "
    "tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly "
    "as it appears in the reference images; exactly ONE wheelchair in the whole video, always the small silver-grey "
    "lightweight one; nobody else ever sits in the wheelchair; the wheelchair moves on its own only in shot 3, "
    "smoothly and slowly, without anyone touching it; the three people never swap clothes, faces or roles; no extra "
    "people ever appear; no background music; every person's appearance, hair and clothing must stay exactly "
    "consistent with the reference images throughout all four shots; the four shots are joined by immediate hard "
    "cuts with no fades or dissolves."
)


def main() -> None:
    out = {
        "job_uid": "job_manual_T19",
        "template_id": "manual",
        "template_name": "manual",
        "mode": "manual",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": [],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": [str(p) for p in REFS],
        "ref_audios": [str(p) for p in AUDIOS],
        "prompt": PROMPT,
        "lines_meta": [],
    }
    jp = ROOT / "state/onetake_prompt_job_manual_T19.json"
    jp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs/onetake_check_T19.txt").write_text(PROMPT, encoding="utf-8")
    print(f"✓ spec: {jp}")
    for p in REFS + AUDIOS:
        assert p.exists(), f"缺: {p}"
    print(f"✓ 参考图 {len(REFS)} + 音频 {len(AUDIOS)} 全部就位")


if __name__ == "__main__":
    main()
