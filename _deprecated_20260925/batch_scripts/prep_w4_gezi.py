"""W4《鸽子都比您这车快》— 爽文短剧（G2）prompt 组装

宝哥 2026-09-26 令：按 W3 的**4 镜 8 句对撞结构**再出一条 15 秒爽文短剧脚本。

结构（沿用宝哥定稿范本，逐条对应）：
  镜1 她人身羞辱  → 他一句反击
  镜2 她当众下注（赌注可演）→ 他钉死
  镜3 她体力崩溃求饶 → 他得意碾压（+ 卖点画面）
  镜4 她当场兑现赌注（画面演）+ 服气发问 → 他品牌句（面向镜头）

组合：老外时尚组（保新，池 2 次）× lcd_screen（液晶屏，池 0 次）× B39 公园喂鸽子（未拍）× G2 短剧狗血
差异化 vs W3：场景=公园广场（非赛道）｜赌注=蹲马步（非俯卧撑）｜崩溃姿态=扶膝弯腰喘（非坐地）｜卖点=液晶屏电量
视线规则（宝哥 2026-09-25）：对话看对方，仅品牌句面向镜头 → 走 lib/prompt_parts.compose()
台词 8 句 70 纯汉字 / 每镜 2 句 / 单句 ≤13
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import prompt_parts as pp

LIB = "assets/cast/library"
VOICE = "assets/cast/voice/real"

CAST_LIB = {
    "girl": {
        "short": "foreign girl",
        "img": f"{LIB}/fashion_western_girl_20.png",
        "audio": f"{VOICE}/w04_foreign_female.mp3",
        "desc": "a 20-year-old Caucasian girl with long wavy blonde hair, wearing a bright yellow puffer jacket over a white top, cocky and loud, clearly a foreigner living in China",
        "voice": "a YOUNG woman's voice — clear, bright, quick and cocky, with a light foreign accent",
    },
    "grandpa": {
        "short": "foreign grandpa",
        "img": f"{LIB}/fashion_western_grandpa.png",
        "audio": f"{VOICE}/w01_foreign_male.mp3",
        "desc": "a 70-year-old Caucasian grandpa with short white hair and a neat white beard, wearing a dark green quilted jacket over a grey shirt, calm and dignified, clearly a foreigner living in China",
        "voice": "an ELDERLY man's voice — low, deep and unhurried, with a light foreign accent",
    },
}

PROD = ROOT / "assets/products"
REFS_TAIL = [
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]

WHEEL = (
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching reference images 3, 4 and 5: "
    "silver-grey frame, black cushion seat, red springs, brand lettering as in references). Its four small wheels "
    "rest on the ground and the seat frame is locked into place; it is an ELECTRIC wheelchair with visible motor "
    "hubs, the distinctive RED shock-absorbing springs and the JOYSTICK CONTROLLER with its small lit DISPLAY "
    "clearly visible on the right armrest in every shot — never a plain manual wheelchair with large hand rims, "
    "never a bicycle, scooter or motorcycle, and it never deforms, morphs or changes shape. The SAME single "
    "wheelchair in every shot, standing upright on the ground, never laid flat and never floating.\n"
    "RIDING RULE: the grandpa is ALWAYS SEATED on the cushion with both hands on the joystick while it moves; "
    "NOBODY ever pushes it from behind, stands beside it while it rolls, or holds the backrest.\n"
)

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    cast_block = (
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned, mirrored or twinned into a second similar figure; no extra "
        "bystanders, no crowd): a 20-year-old girl and a 70-year-old man, both foreigners living in China who "
        "speak Mandarin. They must look CLEARLY DIFFERENT at all times — different age, gender, hair colour and "
        "hairstyle, clothing colour; never the same face, hair or outfit.\n"
    )
    for i, c in enumerate(cast):
        cast_block += (
            f"- (S{i + 1}) {c['desc']}, exactly as in reference image {i + 1}. "
            f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n"
        )
    cast_block += "The two voices are clearly DIFFERENT in pitch and age; never swap them.\n" + WHEEL

    shots = ""
    for i, shot in enumerate(script["shots"]):
        seg = f"[Shot {i + 1}, {SHOT_TIMES[i]}] {shot['desc']} "
        for j, (who, text) in enumerate(shot["lines"]):
            idx = script["cast"].index(who) + 1
            verb = "says" if j == 0 else "replies"
            short = CAST_LIB[who].get("short", "person")
            seg += f"(S{idx}) the {short} {verb}: <d>[Chinese] {text}</d> "
        seg += "ONLY the speaker's mouth moves; the other person's lips stay completely closed. "
        if i < 3:
            seg += "Hard cut. "
        shots += seg + "\n\n"

    return pp.compose(
        shots=shots,
        cast=cast_block,
        soundscape=(
            "Quiet open-air city park room tone, light wind, distant birds and pigeons cooing, faint footsteps on "
            "the paved square; clear natural voices. No music."
        ),
        extra_tail=(
            "The grandpa drives the wheelchair smoothly, steadily and never wobbling; the girl never touches or "
            "pushes the moving wheelchair. The emotional beats escalate shot by shot: contempt, challenge, panic, "
            "surrender."
        ),
    )


SCRIPTS = [
    {
        "uid": "W4_gezi",
        "cast": ["girl", "grandpa"],
        "scene": "a paved square in a city park on a clear morning, a low stone bench and a big leafy tree behind, "
                 "green shrubs and a few pigeons far in the blurred background, no crowd",
        "shots": [
            {"desc": "COLD OPEN: a tight close-up of the girl's sneering sidelong glance at the wheelchair (half a "
                     "second), then cut wide: she stands beside the wheelchair holding a small paper bag of pigeon "
                     "feed in one hand and taps the wheelchair's wheel with the toe of her shoe in contempt, chin "
                     "high, eyes on the grandpa as she speaks; he lifts his chin and gives her a sharp defiant look "
                     "as he answers. The camera pushes in slightly.",
             "lines": [("girl", "大爷，那鸽子都比您这车快。"), ("grandpa", "那你跟我比一段。")]},
            {"desc": "The girl throws her head back in a short laugh, then jabs a finger straight at the grandpa's "
                     "chest and flicks her thumb toward the big tree across the square in a loud public bet, still "
                     "facing him; he tilts his head and nods once, unimpressed, eyes locked on hers. The camera "
                     "glides gently sideways.",
             "lines": [("girl", "您要赢我，我蹲马步蹲到天黑。"), ("grandpa", "你可说话算话。")]},
            {"desc": "The girl has given up and is standing bent double with both hands braced on her knees in the "
                     "middle of the square, chest heaving as she gasps for air, hair hanging down, the paper feed "
                     "bag still crumpled in one fist; the wheelchair has already stopped a couple of metres AHEAD "
                     "of her, and the grandpa, still seated, turns his upper body right around to look back at her, "
                     "taps the lit display on the armrest with one finger, and looks completely unbothered as she "
                     "lifts her head to speak. The camera tracks gently sideways keeping BOTH of them in frame.",
             "lines": [("girl", "您这车怎么不累啊？"), ("grandpa", "满格电，跑一天都行。")]},
            {"desc": "The girl is now holding a horse-riding stance — knees bent wide, thighs trembling, both "
                     "hands pressed on her thighs — and she turns her head up toward the grandpa as she speaks; "
                     "the grandpa sits on the wheelchair right beside her and, for the branding line only, turns "
                     "his face to the camera and looks straight into the lens. The camera pulls back slowly to "
                     "show both of them.",
             "lines": [("girl", "大爷，您这车得多少钱啊。"), ("grandpa", "爱优护轻便侠。")]},
        ],
    },
]


def main() -> None:
    for s in SCRIPTS:
        prompt = build_prompt(s)
        cast = [CAST_LIB[k] for k in s["cast"]]
        refs = [str(ROOT / c["img"]) for c in cast] + [str(p) for p in REFS_TAIL]
        audios = [str(ROOT / c["audio"]) for c in cast]
        spec = {
            "job_uid": s["uid"],
            "template_id": "manual", "template_name": "manual", "mode": "manual",
            "workflow": "minimax_h3_image_audio_to_video_v2_15s",
            "fallback_workflows": [],
            "duration": 15,
            "resolution": "768p竖",
            "ref_images": refs,
            "ref_audios": audios,
            "prompt": prompt,
            "lines_meta": [],
        }
        jp = ROOT / f"state/onetake_prompt_job_{s['uid']}.json"
        jp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / f"docs/onetake_check_{s['uid']}.txt").write_text(prompt, encoding="utf-8")
        lines = [t for sh in s["shots"] for _, t in sh["lines"]]
        (ROOT / f"docs/onetake_lines_{s['uid']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        cjk = sum(len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines)
        per = [len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines]
        print(f"✓ {s['uid']} → {jp.name}（图 {len(refs)} / 音 {len(audios)} / 纯汉字 {cjk} 单句 {per}）")


if __name__ == "__main__":
    main()
