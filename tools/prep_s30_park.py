"""30s 双段狗血爽文短剧《老邻居的新车》— 段1《窄缝》+ 段2《躺平》

宝哥 2026-09-26 令：30 秒 = 两条 15s one-take 拼接（先出脚本审核，审核通过再付费生成）。

剧作结构（狗血爽文 30s 二段式 = 压抑→爆发拉满）：
  段1《窄缝》：邻居挡车位炫耀 → 主角反下注 → 窄缝泊车小胜 → 邻居嘴硬加码（钩子）
  段2《躺平》：加注兑现（请三顿）→ 靠背放倒平躺碾压 → 邻居认输 → 品牌句

卖点：段1 = joystick_360（360°操纵杆·窄缝泊车，**首次用作主打**）
      段2 = recline_145（145度后躺）
片型：G2 短剧狗血爽文 ｜ 角度：B44 停车坪攀比（新注册）
选角：S1 = city_grandpa_75（灰毛衣·和善固执）｜S2 = fashion_gent_55（银灰背头·墨绿西装·傲慢）
音色：S1 = r12_elder_male.mp3 ｜ S2 = r09_adult_male.mp3

技术口径（check_dialogue.mjs 门禁）：
  · 15s 档 nativeSeconds=15.083 → 可用 14.483s → **65-72 纯汉字**（4.5-5.0 字/秒）
  · 单句 ≤13 字｜禁止 ——｜标点只用 ，。？！｜数字写中文
  · 每镜 2 句（D2 批教训：每镜 3 句必丢句）
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
    "grandpa": {
        "short": "grandpa",
        "img": f"{LIB}/city_grandpa_75.png",
        "audio": f"{VOICE}/r12_elder_male.mp3",
        "desc": "a 75-year-old Chinese grandpa with short white hair, deep wrinkles and a calm plain face, "
                "wearing a light grey knitted sweater, unhurried and quietly stubborn",
        "voice": "an ELDERLY man's voice — low, calm and completely unhurried",
    },
    "gent": {
        "short": "gentleman",
        "img": f"{LIB}/fashion_gent_55.png",
        "audio": f"{VOICE}/r09_adult_male.mp3",
        "desc": "a 55-year-old Chinese man with neat silver-grey hair combed straight back, wearing a dark "
                "green blazer over a crisp white shirt, chin slightly lifted, smug and condescending",
        "voice": "a MIDDLE-AGED man's voice — clear, quick and smug",
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
    "RIDING RULE: the grandpa is ALWAYS SEATED on the cushion with his hand on the joystick while it moves; "
    "NOBODY ever pushes it from behind, stands beside it while it rolls, or holds the backrest.\n"
    "SCENE PROPS: in the background behind the two men stand TWO parked cars — only their LOWER HALVES are "
    "visible, cut off by the top of the frame; they are simple dark shutters and wheels and never move.\n"
)

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    cast_block = (
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned, mirrored or twinned into a second similar figure; no extra "
        "bystanders, no crowd): a 75-year-old man and a 55-year-old man, both Chinese. They must look CLEARLY "
        "DIFFERENT at all times — different age, hair colour, hair style and clothing colour "
        "(GREY KNITTED SWEATER versus DARK GREEN BLAZER WITH WHITE SHIRT); never the same face, hair or outfit.\n"
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
        seg += "ONLY the speaker's mouth moves; the other person's lips stay completely closed and still. "
        if i < 3:
            seg += "Hard cut. "
        shots += seg + "\n\n"

    return pp.compose(
        shots=shots,
        cast=cast_block,
        soundscape=script["soundscape"],
        extra_tail=script["extra_tail"],
    )


SCRIPTS = [
    # ─────────────────────────── 段1《窄缝》 ───────────────────────────
    {
        "uid": "S30_1_zhaifeng",
        "cast": ["gent", "grandpa"],
        "soundscape": (
            "Quiet residential parking bay room tone, a light breeze, faint birds and distant traffic; clear "
            "natural voices and soft rubber tyres rolling on concrete. No music."
        ),
        "extra_tail": (
            "The two men never touch each other. The wheelchair never touches the parked cars, never scrapes them "
            "and is never damaged. The emotional beats escalate shot by shot: condescension, challenge, disbelief."
        ),
        "shots": [
            {"desc": "COLD OPEN: a tight close-up of the gentleman's chin lifting with a smug sidelong look "
                     "(half a second), then cut wide to the parking bay: the gentleman stands with BOTH ARMS "
                     "RAISED STRAIGHT OUT SIDEWAYS, palms forward, blocking the empty parking space behind him, "
                     "chin high and eyes on the grandpa; the grandpa sits on the wheelchair facing him, one hand "
                     "resting calmly on the joystick, and answers with a small confident lift of his eyebrows. "
                     "The camera pushes in slightly. Neither person moves away from their spot.",
             "lines": [("gent", "这车位我今天占下了。"), ("grandpa", "我这就占巴掌大。")]},
            {"desc": "The gentleman jabs one finger toward a narrow gap between the two parked cars behind them, "
                     "leaning forward with a mocking smile as he challenges; the grandpa tilts his head and nods "
                     "once, completely unbothered, eyes on the gentleman. The camera glides gently sideways.",
             "lines": [("gent", "那缝儿你能塞得进去？"), ("grandpa", "你要塞进去，今天就你请客。")]},
            {"desc": "The gentleman folds his arms across his chest and leans his upper body back with a smirk, "
                     "watching; the grandpa pushes the joystick with his thumb and the wheelchair rolls slowly "
                     "FORWARD INTO the narrow gap between the two parked cars, its sides passing only a hand's "
                     "width from the cars, then it stops neatly inside the gap. The camera tracks sideways keeping "
                     "BOTH of them in frame.",
             "lines": [("gent", "我倒看你咋挪进去。"), ("grandpa", "你往后站站，别眨眼。")]},
            {"desc": "The grandpa sits parked neatly inside the narrow gap and turns his head back toward the "
                     "gentleman, raising ONE INDEX FINGER and looking satisfied; the gentleman's eyes go wide and "
                     "his mouth drops open, then he jabs his finger at the wheelchair and speaks again with his chin "
                     "thrust out. The camera pulls back slowly to show both of them.",
             "lines": [("grandpa", "一厘米都不多占。"), ("gent", "窄缝子算啥，你敢躺下？")]},
        ],
    },
    # ─────────────────────────── 段2《躺平》 ───────────────────────────
    {
        "uid": "S30_2_tangping",
        "cast": ["gent", "grandpa"],
        "soundscape": (
            "Same quiet residential parking bay room tone, a light breeze and distant birds; clear natural voices "
            "and a soft mechanical click. No music."
        ),
        "extra_tail": (
            "The wheelchair's backrest reclines smoothly and stays attached — the chair never breaks, collapses or "
            "loses parts, and the grandpa never falls off. The two men never touch each other. The emotional beats "
            "escalate shot by shot: doubt, surprise, total surrender."
        ),
        "shots": [
            {"desc": "The gentleman holds up THREE FINGERS right in front of his chest, chin high and eyebrows "
                     "raised, making his new bet; the grandpa, still seated in the wheelchair inside the narrow "
                     "gap, nods once and looks straight back at him. The camera pushes in slightly.",
             "lines": [("gent", "你要真能躺下，我请你三顿。"), ("grandpa", "成，那你说话算话。")]},
            {"desc": "The gentleman leans down and squints at the wheelchair's seat back, still doubting; the "
                     "grandpa reaches back with his right hand and pulls the seat's side lever, and the BACKREST "
                     "TILTS SLOWLY BACKWARD while he keeps his body upright and controlled. The camera glides "
                     "gently sideways.",
             "lines": [("gent", "就这破椅子，躺得住人？"), ("grandpa", "拉杆一拉，后背就落。")]},
            {"desc": "The grandpa is now lying back FLAT on the fully reclined wheelchair backrest, head resting "
                     "on the armrest, both hands folded on his stomach, eyes closed and completely relaxed; the "
                     "gentleman bends forward with both hands on his knees, eyes bulging, staring at the reclined "
                     "chair. The camera tracks sideways keeping BOTH of them in frame.",
             "lines": [("gent", "哎哟，这后背真放平了？"), ("grandpa", "我这叫躺着回家，多舒坦。")]},
            {"desc": "The gentleman straightens up, waves one hand in surrender and shakes his head with a wry "
                     "smile; the grandpa opens his eyes, sits part-way up on the reclined backrest and, for the "
                     "branding line only, turns his face to the camera and looks straight into the lens. The "
                     "camera pulls back slowly to show both of them.",
             "lines": [("gent", "得，这三顿饭我请。"), ("grandpa", "爱优护轻便侠。")]},
        ],
    },
]


def main() -> None:
    for s in SCRIPTS:
        prompt = build_prompt(s)
        cast = [CAST_LIB[k] for k in s["cast"]]
        refs = [str(ROOT / c["img"]) for c in cast] + [str(p) for p in REFS_TAIL]
        audios = [str(ROOT / c["audio"]) for c in cast]
        for p in refs[2:]:
            assert Path(p).exists(), f"缺产品图 {p}"
        for p in refs[:2] + audios:
            assert Path(p).exists(), f"缺资产 {p}"
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
        # check 稿头部带 duration 声明 → 让 check_dialogue 的 R10/R28 语速规则真正生效
        # （2026-09-26 发现：不带 duration 时 requested=undefined，语速检查被整段跳过）
        header = f'<!-- duration="{spec["duration"]}" 语速门禁：纯汉字 65-72（4.5-5.0 字/秒铺满）-->\n'
        (ROOT / f"docs/onetake_check_{s['uid']}.txt").write_text(header + prompt, encoding="utf-8")
        lines = [t for sh in s["shots"] for _, t in sh["lines"]]
        (ROOT / f"docs/onetake_lines_{s['uid']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        cjk = sum(len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines)
        per = [len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines]
        print(f"✓ {s['uid']} → {jp.name}（图 {len(refs)} / 音 {len(audios)} / 纯汉字 {cjk} 单句 {per}）")


if __name__ == "__main__":
    main()
