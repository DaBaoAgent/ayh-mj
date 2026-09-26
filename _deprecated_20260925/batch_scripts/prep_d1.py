"""D1《菜场试坐》 — 短剧狗血爽文（赌约打脸版 v2） spec 生成

对照脚本稿：docs/script-D1-菜场试坐-20260925.md（v2）
组合：核心卡司组 × load_100承重 × B14菜市场 × G2短剧狗血爽文
学习依据：assets/scripts/drama_craft_2026.md（20 部爆款短剧打法）
用法：.venv/Scripts/python.exe tools/prep_d1.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.prompt_parts import COLD_OPEN, PACE, REALISM  # noqa: E402

CAST = ROOT / "assets/cast"
PROD = ROOT / "assets/products"

# 参考图 5 张：人物2 + 产品3（宝哥铁律：折叠+正侧+45度必须全给）
REFS = [
    CAST / "emotions/elder_full.png",          # 图1 → (S1) 老王
    CAST / "library/core_shop_owner_50.png",   # 图2 → (S2) 摊主
    PROD / "折叠-无阴影.png",                    # 图3
    PROD / "正侧-3-无阴影.png",                  # 图4
    PROD / "45度-加水杯-无阴影.png",              # 图5
]
AUDIOS = [
    CAST / "voice/elder_voice.mp3",           # 音1 → (S1) 老王
    CAST / "voice/real/r09_adult_male.mp3",   # 音2 → (S2) 摊主（真人样本·中年男声）
]

PROMPT = (
    "integrated_multimodal_description: Live-action short comedy-drama in vertical framing, a lively open-air "
    "vegetable market alley in soft daylight. " + PACE + " " + REALISM + " " + COLD_OPEN + "\n\n"

    "CAST (STRICTLY BIND — exactly TWO people and ONE wheelchair; each person appears EXACTLY ONCE per shot, "
    "never duplicated or cloned; no extra bystanders): both Chinese, speaking standard Mandarin.\n"
    "- (S1) Wang: the 65-year-old man in the FIRST reference image, short grey-white hair, dark blue jacket — "
    "calm and sly.\n"
    "- (S2) Boss: the 50-year-old shop owner in the SECOND reference image, round friendly face, dark blue apron "
    "over a plaid shirt — skeptical and loud-mouthed.\n"
    "VOICES: (S1) uses audio 1 (an elderly man's timbre), (S2) uses audio 2 (a middle-aged man's timbre); the "
    "two voices are clearly DIFFERENT and are never swapped.\n"
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair in the THIRD, FOURTH and FIFTH reference "
    "images — silver-grey metal frame, black cushion seat, four small wheels, its distinctive RED shock-absorbing "
    "springs and its own brand lettering, exactly as in the references; it easily holds a grown man's weight "
    "without bending and is never a plain manual wheelchair, bicycle or toy; the SAME single wheelchair in every "
    "shot.\n\n"

    "[Shot 1, 0 to 3.5 seconds] The video opens on an extreme close-up of a hand patting the wheelchair's black "
    "cushion seat, then cuts to a wide shot of a busy vegetable market alley: (S1), the 65-year-old man in the "
    "dark blue jacket, stands beside the small silver-grey wheelchair in front of a vegetable stall; (S2), the "
    "shop owner in the dark blue apron, steps out from behind the stall and studies the wheelchair with doubtful "
    "eyes. (S2) says, skeptical: <d>[Chinese] 老王，这车能坐人吗？我看悬。</d> The camera pushes in slowly. "
    "ONLY the speaker's mouth moves; the other person's lips stay closed. Hard cut.\n\n"

    "[Shot 2, 3.5 to 8 seconds] (S1) grins, pats the seat twice and beckons him over: "
    "<d>[Chinese] 来来来，你坐坐看。</d> — (S2) puffs out his chest, taps his palm on the vegetables basket and "
    "boasts: <d>[Chinese] 我坐就我坐！稳了菜钱免了！</d> — (S1) nods, deadpan: "
    "<d>[Chinese] 你说的啊。</d> The camera pans right from (S1) to (S2). ONLY the speaker's mouth moves; the "
    "other person's lips stay closed. Hard cut.\n\n"

    "[Shot 3, 8 to 11.5 seconds] (S2) wipes his hands, steps over and sits down on the wheelchair in one smooth "
    "motion — the wheelchair stays perfectly steady on the ground and does not wobble or bend at all under his "
    "weight. His eyes go wide in surprise: <d>[Chinese] 哎哟喂，还真挺稳当！</d> — (S1) pats the armrest, "
    "pleased: <d>[Chinese] 一百公斤，随便坐。</d> The camera tilts down slightly following him sitting, "
    "then steadies. ONLY the speaker's mouth moves; the other person's lips stay closed. Hard cut.\n\n"

    "[Shot 4, 11.5 to 14.5 seconds] The shot pulls back to a wider two-shot: (S1) lifts the basket of vegetables "
    "from the stall and places it onto the footrest of the wheelchair; (S2) gives a thumbs-up, impressed. (S1) "
    "pats the seat, proud, and says, finishing right before the video ends: "
    "<d>[Chinese] 皮实又省心，认准爱优护轻便侠。</d> ONLY the speaker's mouth moves; the other person's lips "
    "stay closed.\n\n"

    "Scene: a lively vegetable market alley with fresh-produce stalls. Only these two people speak, taking turns "
    "in exactly this order with no overlap; every line is spoken exactly once, verbatim, with no extra, omitted, "
    "repeated or invented lines. No on-screen text; dialogue is audio only.\n\n"

    "overall_soundscape: Lively market ambience — distant vendors calling, soft chatter, and the firm creak of a "
    "sturdy seat taking a man's weight; clear natural voices.\n\n"
    "non_diegetic_music: N/A\n\n"

    "Hard constraints: exactly TWO people and ONE wheelchair, always the small silver-grey lightweight electric "
    "one, which never collapses or bends under the man's weight; nobody is ever duplicated or swapped; no extra "
    "people; no background music; no watermarks, subtitles, captions, text, stickers, price tags, logos, UI "
    "elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as in the references; "
    "appearances stay exactly consistent with the references; hard cuts only, no fades."
)


def main() -> None:
    spec = {
        "job_uid": "job_D1",
        "template_id": "manual", "template_name": "manual", "mode": "manual",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": [str(p) for p in REFS],
        "ref_audios": [str(p) for p in AUDIOS],
        "prompt": PROMPT,
        "lines_meta": {
            "combo": "核心卡司组 × load_100承重 × B14菜市场 × G2短剧狗血爽文（pick_combo job_manual_D1_jingqu）",
            "title": "菜场试坐",
            "version": "v2-赌约打脸",
            "mode": "short_drama",
            "shots": 4,
            "lines": 7,
            "chars": 66,
            "ref_count": 5,
            "audios": 2,
            "risk_test": "镜3（坐上车纹丝不动）+ 镜4（拎菜筐）建议 480p 快测",
        },
    }
    jp = ROOT / "state/onetake_prompt_job_D1.json"
    jp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs/onetake_check_D1.txt").write_text(PROMPT, encoding="utf-8")
    print(f"✓ spec: {jp}")
    print(f"  prompt 长度: {len(PROMPT)} 字符")
    missing = [str(p) for p in REFS + AUDIOS if not p.exists()]
    print("  ⚠ 缺失: " + ", ".join(missing) if missing else "  ✓ 参考图/音色全部就位")


if __name__ == "__main__":
    main()
