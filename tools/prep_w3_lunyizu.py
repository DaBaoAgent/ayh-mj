"""W3《轮椅组就您一个人》v4 定稿版（宝哥口对白 · 结构范本）— 短剧狗血（G2）

宝哥 2026-09-26 给定对白并令「以后都按照这种结构来做」→ 本文件同时是**结构范本**。

结构（4 镜 8 句双人对撞）：
  镜1 人身羞辱（当众、狠）        → 他一句反击（带火气）
  镜2 当众下注（赌注具体·身体动作可演）→ 他钉死（4-6 字）
  镜3 她体力崩溃求饶              → 他得意碾压
  镜4 她当场兑现赌注（画面演）+ 服气发问 → 他品牌句（面向镜头，品牌名即收，不加口号）

技术合规化（对宝哥原话的最小改动，已在脚本里标注）：
  · 「100个俯卧撑」→「一百个」：check_dialogue R18 禁阿拉伯数字（会被念错/报 ERROR）
  · 「你要能跑赢我，我当场做100个俯卧撑」17 字 → 「你赢我，我当场做一百个俯卧撑」13 字（单句 ≤13 硬约束）
  · 口语补字到 65-72 纯汉字口径：你这是 / 真不行了 / 这回 / 到底
视线规则（宝哥 2026-09-25）：对话看对方，仅品牌句面向镜头 → 走 lib/prompt_parts.compose()
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
        "short": "sporty girl",
        "img": f"{LIB}/fashion_girl_sporty.png",
        "audio": f"{VOICE}/r05_young_female.mp3",
        "desc": "a 20-year-old Chinese girl with long black hair in a high ponytail with a small bun and face-framing bangs, wearing a bright white zip-up hooded athletic jacket, cocky and loud",
        "voice": "a YOUNG woman's voice — clear, bright, quick and cocky",
    },
    "grandpa": {
        "short": "stylish grandpa",
        "img": f"{LIB}/fashion_grandpa_cool.png",
        "audio": f"{VOICE}/r12_elder_male.mp3",
        "desc": "a 70-year-old Chinese grandpa with short silver-white hair combed back and a neatly trimmed grey beard, wearing a dark navy blazer over a crisp white shirt with the top button open, calm and dignified",
        "voice": "an ELDERLY man's voice — low, deep and unhurried",
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
    "hubs, the distinctive RED shock-absorbing springs and the JOYSTICK CONTROLLER with its small speed switch "
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
        "bystanders, no crowd): a 20-year-old girl and a 70-year-old man, both Chinese. They must look CLEARLY "
        "DIFFERENT at all times — different age, gender, hair colour and hairstyle, clothing colour; never the "
        "same face, hair or outfit.\n"
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
            "Quiet open-air community sports ground room tone, light wind, distant birds and heavy breathing "
            "and footsteps on the paved track; clear natural voices. No music."
        ),
        extra_tail=(
            "The grandpa drives the wheelchair smoothly, steadily and never wobbling; the girl never touches or "
            "pushes the moving wheelchair. The emotional beats escalate shot by shot: contempt, challenge, panic, "
            "surrender."
        ),
    )


SCRIPTS = [
    {
        "uid": "W3_lunyizu",
        "cast": ["girl", "grandpa"],
        "scene": "the start line of a short painted lane on a small community sports ground in a residential "
                 "compound, on a clear morning, white lane lines on the paved track, a low red-and-white finish "
                 "marker down the lane and green shrubs behind, no crowd",
        "shots": [
            {"desc": "COLD OPEN: a tight close-up of the girl's sneering sidelong glance at the wheelchair (half a "
                     "second), then cut wide to the start line: she slaps the wheelchair's cushion twice with one "
                     "flat hand in contempt, chin high, eyes on the grandpa as she speaks; he flicks her hand off "
                     "the seat with the back of his hand, chin up, and gives her a sharp defiant look as he "
                     "answers. The camera pushes in slightly.",
             "lines": [("girl", "大爷，一把老骨头了，别来折腾了。"), ("grandpa", "切，你这是看不起我是吧。")]},
            {"desc": "The girl jabs a finger straight at the grandpa's chest in a loud public bet, chin thrust "
                     "out, still facing him; he tilts his head and nods once, unimpressed, eyes locked on hers. "
                     "The camera glides gently sideways.",
             "lines": [("girl", "你赢我，我当场做一百个俯卧撑。"), ("grandpa", "可别赖账啊。")]},
            {"desc": "On the painted lane the girl has given up running and is sitting COLLAPSED ON THE GROUND, "
                     "legs sprawled out in front of her, leaning back on both hands, head hanging, chest heaving "
                     "as she gasps for air with her mouth wide open; the wheelchair has already stopped a couple "
                     "of metres AHEAD of her, and the grandpa, still seated, turns his upper body right around to "
                     "look back down at her and laughs out loud. She lifts her head toward him as she speaks. The "
                     "camera tracks gently sideways keeping BOTH of them in frame.",
             "lines": [("girl", "我不行了，真不行了！"), ("grandpa", "这回服了吧？")]},
            {"desc": "The girl is down on the paved track in a push-up position — both hands flat on the ground "
                     "under her shoulders, body straight, arms bending as she lowers herself — and she turns her "
                     "head up toward the grandpa as she speaks; the grandpa sits on the wheelchair right beside "
                     "her and, for the branding line only, turns his face to the camera and looks straight into "
                     "the lens. The camera pulls back slowly to show both of them.",
             "lines": [("girl", "你这到底什么车啊。"), ("grandpa", "爱优护轻便侠。")]},
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
