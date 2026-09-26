"""W2《车会说话》— 单条爆款 prompt 组装（欧美组 × AI语音播报 × G4 脑洞广告）

构思：外国邻居听到轮椅"自己说话"（AI 语音播报），以为车里藏了人 → 神转折揭晓
结构：悬念钩（藏人？）→ 反转1（是车会说话）→ 反转2（1 分钟学会 + 亲测）→ 品牌
保新：角度/卖点/片型/角色组四池全部最少用（voice_ai 池 0 次、G4 池 0 次、欧美组 2 次）
约束：台词 8 句 68 字（15s 档 65-72）/ 每镜 2 句（防漏句）/ 无阿拉伯数字 / 无英文 / 无破折号
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = "assets/cast/library"
VOICE = "assets/cast/voice/real"

# ── 角色（欧美组：外国角色讲中文，跨性别配对，音色 f0 差 ≥60Hz）──
CAST_LIB = {
    "gent": {
        "short": "foreign gentleman",
        "img": f"{LIB}/western_gent_60.png",
        "audio": f"{VOICE}/w01_foreign_male.mp3",
        "desc": "a 60-year-old Caucasian gentleman with short silver-grey hair, a dark navy wool blazer over a light shirt, calm and smiling, clearly a foreigner living in China",
        "voice": "an ELDERLY man's voice — low, deep and steady, with a light foreign accent",
    },
    "aunt": {
        "short": "foreign neighbour",
        "img": f"{LIB}/western_aunt_55.png",
        "audio": f"{VOICE}/w04_foreign_female.mp3",
        "desc": "a 55-year-old Caucasian woman with curly blonde hair, a bright coral-red sport jacket and a colourful scarf, chatty and easily startled, clearly a foreigner living in China",
        "voice": "a MATURE woman's voice — bright, higher-pitched, chatty and quick",
    },
}

PROD = ROOT / "assets/products"
REFS_TAIL = [
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]

STYLE = (
    "integrated_multimodal_description: Live-action fun commercial in vertical framing. "
    "Pacing is tight and bouncy; everyone speaks at a natural, brisk conversational pace. The first line starts "
    "within the first quarter second, every line begins immediately after the previous line's last word and "
    "immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a "
    "second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is "
    "always gently moving — a pull-back, a sideways glide, a slow tracking move and a final pull-back — never static."
    " Shot like real documentary footage: natural available light with soft realistic shadows, lifelike skin texture "
    "with visible pores and fine lines, natural hair detail, true-to-life colors, shallow depth of field like an 85mm "
    "lens at f/2, photorealistic and candid — no plastic skin, no over-smoothing. Faces are expressive and "
    "theatrical with big visible emotion: widened startled eyes, raised eyebrows, dropped-open mouths and little "
    "recoils, held clearly long enough for the camera to catch them.\n\n"
)

WHEEL = (
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching reference images 3, 4 and 5: "
    "silver-grey frame, black cushion seat, red springs, brand lettering as in references). Its four small wheels "
    "rest on the ground and the seat frame is locked into place; it is an ELECTRIC wheelchair with visible motor "
    "hubs, the distinctive RED shock-absorbing springs and the JOYSTICK CONTROLLER with its small button console "
    "clearly visible on the right armrest in every shot — never a plain manual wheelchair with large hand rims, "
    "never a bicycle, scooter or motorcycle, and it never deforms, morphs or changes shape. The SAME single "
    "wheelchair in every shot, standing upright on the ground, never laid flat, never floating.\n"
    "RIDING RULE: the person who uses it is ALWAYS SEATED on the cushion with both hands on the joystick "
    "while it moves; NOBODY ever pushes it from behind, stands beside it while it rolls, or holds the "
    "backrest — it is driven, never pushed.\n"
    "BOTH PEOPLE STAY FULLY VISIBLE in every shot of the whole video; whenever anyone speaks, their face stays "
    "clearly visible to the camera and turned toward it; no speaker is ever out of frame or seen only from behind "
    "while delivering a line. Each person keeps both hands on the wheelchair or at their sides, touching nothing "
    "else, and only the speaker's mouth moves.\n\n"
)

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    lines = [STYLE]
    lines.append(
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned or mirrored into a second similar figure; no extra bystanders): "
        "two foreigners living in China, speaking standard Mandarin. The two people must look CLEARLY DIFFERENT "
        "from each other at all times — different age, gender, face shape, hair colour and hairstyle, clothing "
        "colour; they must NEVER be drawn with the same face, hair or outfit, and never look like twins.\n"
    )
    for i, c in enumerate(cast):
        lines.append(
            f"- (S{i + 1}) {c['desc']}, exactly as in reference image {i + 1}. "
            f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n"
        )
    lines.append(
        "The voices are clearly DIFFERENT in pitch and age; never swap them.\n" + WHEEL
    )
    for i, shot in enumerate(script["shots"]):
        segs = [f"[Shot {i + 1}, {SHOT_TIMES[i]}] {shot['desc']} "]
        for j, (who, text) in enumerate(shot["lines"]):
            idx = script["cast"].index(who) + 1
            verb = "says" if j == 0 else "replies"
            short = CAST_LIB[who].get("short", "person")
            segs.append(f"(S{idx}) the {short} {verb}: <d>[Chinese] {text}</d> ")
        segs.append("ONLY the speaker's mouth moves; the other person's lips stay completely closed. ")
        if i < 3:
            segs.append("Hard cut. ")
        lines.append("".join(segs) + "\n\n")
    lines.append(
        f"Scene: {script['scene']}. Only these people speak, taking turns with no overlap, in exactly this order. "
        "EVERY LINE IS SPOKEN EXACTLY ONCE, no line is ever repeated, doubled or echoed. All dialogue spoken "
        "verbatim, no extra words, no omissions. No on-screen text; dialogue is audio only.\n\n"
    )
    lines.append(
        "overall_soundscape: Quiet residential courtyard room tone, birds and a light breeze; when the gentleman "
        "presses the console button, the wheelchair's built-in speaker plays a short crisp COMPUTERISED electronic "
        "prompt — a brief robotic device chime-and-beep, clearly a machine speaker, never a human voice and never "
        "any intelligible speech. Natural clear human dialogue over it.\n\n"
        "non_diegetic_music: N/A\n\n"
        "Hard constraints: exactly ONE wheelchair, always the small silver-grey ELECTRIC lightweight one; each "
        "person appears exactly once per shot and is never duplicated; the two people never swap clothes, faces, "
        "voices or roles; no extra people; the wheelchair speaker never produces a human voice; no background "
        "music; render no watermarks, subtitles or text anywhere; looks stay exactly consistent with the reference "
        "images; hard cuts only, no fades."
    )
    return "".join(lines)


SCRIPTS = [
    {
        "uid": "W2_carvoice",
        "cast": ["aunt", "gent"],
        "scene": "the paved forecourt of a residential compound on a bright afternoon, low green shrubs and a "
                 "bicycle rack behind, warm sunlight from the left",
        "shots": [
            {"desc": "The shot opens TIGHT on the wheelchair's EMPTY cushion and its red shock springs — nobody is "
                     "sitting on it — then the camera pulls back to a wide shot: the foreign neighbour is already "
                     "standing beside the wheelchair, bent forward with both hands on her knees, peering around and "
                     "under the empty seat with wide startled eyes and a dropped-open mouth; the foreign gentleman "
                     "stands two steps away holding a small string bag of vegetables, calm and smiling. The camera "
                     "settles in on her startled face.",
             "lines": [("aunt", "大爷，你车里是不是藏人了？"), ("gent", "藏啥人，是车会说话。")]},
            {"desc": "The gentleman steps closer and presses the small button on the wheelchair's joystick console "
                     "with one finger; the wheelchair's built-in speaker clicks and beeps a short electronic prompt. "
                     "The neighbour straightens up and recoils half a step, eyes bulging, eyebrows shooting up. The "
                     "camera glides gently sideways and holds on her stunned face as he taps the console a second "
                     "time.",
             "lines": [("aunt", "它还会教人？"), ("gent", "我一分钟就会了。")]},
            {"desc": "The gentleman sits down on the cushion, both hands on the joystick, and the wheelchair rolls "
                     "smoothly forward a couple of metres and then stops; the neighbour walks along beside it with "
                     "her hands clasped, watching his hands on the console. The camera tracks gently sideways, "
                     "keeping BOTH the gentleman on the seat and the neighbour in frame.",
             "lines": [("aunt", "真不用学？"), ("gent", "按一下，它报一句。")]},
            {"desc": "The gentleman stays seated with both hands on the joystick and nods; the neighbour takes out "
                     "her phone, holds it up at chest height and taps the screen once, laughing and shaking her head "
                     "in admiration. The camera pulls back slowly to show both people and the wheelchair in the sunny "
                     "courtyard.",
             "lines": [("aunt", "我也给我妈买一台。"), ("gent", "爱优护轻便侠，爸妈一学就会。")]},
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
        cjk = sum(len(t) for sh in s["shots"] for _, t in sh["lines"])
        print(f"✓ {s['uid']} → {jp.name}（图 {len(refs)} / 音 {len(audios)} / 台词 {cjk} 字）")


if __name__ == "__main__":
    main()
