"""30s 双段分镜脚本《孝顺话》—— 改写自爆款短剧《离婚后，爸妈带我走上巅峰》（红果·73集）

宝哥 2026-09-26 令：「用《离婚后，爸妈带我走上巅峰》改写撰写 30 秒分镜脚本，结构逻辑要和原作一样」

═══ 原作结构逻辑（`assets/scripts/hot_dramas_detail/01_打脸逆袭类_7部.md` 第 10-44 行 + 第 270 行打法 1）═══
  ① 开场即双重钩子：离婚当日**当众羞辱** + **失散 20 年、看似平凡的父母突然现身护子**（同一场完成）
  ② 身份**分层解锁，每层只揭一半**：
       第1层 护短（离婚当天父母现身） → 第2层 撑场（同学聚会父亲霸气撑腰）
       → 第3层 亮王牌（**市井小摊前**身份终揭晓，最不起眼的场景反差最大）
  ③ 暗线：父母「暗中默默考验本心」——谁势利、谁真心，先甄别再给资源
  ④ 记忆点 = **一句原话 + 一个动作**（"没本事、父母是穷鬼" → 父母现身）

═══ 本片刻意保留的结构对应（结构逻辑不改，内容换成轻便侠）═══
  原作：前妻一家当众嘲讽"没本事、父母是穷鬼"        → 本片：儿媳当众嫌弃"妈，您这样走，像我们不孝"
  原作：失散 20 年看似平凡的父母**突然现身**护子      → 本片：**"看着不起眼"的车自己滑过来**（无人碰·奇观钩）
  原作：同学聚会父亲霸气撑腰（更公开的场合）          → 本片：儿媳当众坐上去、车纹丝不动（当众撑场）
  原作：市井小摊前身份终揭晓（场景反差最大）          → 本片：菜市场摊前揭晓来历 + 品牌真身
  原作：父母暗中考验本心（甄别势利）                  → 本片：「闺女攒半年给我买的」——真心 vs 势利对照
  原作：每层只揭一半                                  → 本片：①自己会走（不说是什么车）②压不垮（不说多强）③来历+品牌

卖点：第1层 `remote_15m`（无人遥控·奇观）｜第2层 `load_100`（承重，质疑者亲自坐）
片型：G2 短剧狗血爽文 ｜ 角度：B45 菜市场被嫌（新注册）
选角：S1 = city_grandma_maternal_65（深蓝盘扣·温和）｜S2 = city_daughter_in_law_32（米色毛衣·温柔干练）
音色：S1 = r01_elder_female.mp3（样本原话正是"我今年七十五，腿脚还利索"）｜S2 = r05_young_female.mp3
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
    "granny": {
        "short": "grandmother",
        "img": f"{LIB}/city_grandma_maternal_65.png",
        "audio": f"{VOICE}/r01_elder_female.mp3",
        "desc": "a 65-year-old Chinese grandmother with a round face and her grey hair in a neat low bun, "
                "wearing a dark navy mandarin-collar jacket, calm and quietly dignified",
        "voice": "an ELDERLY woman's voice — calm, soft and unhurried",
    },
    "daughter_in_law": {
        "short": "young woman",
        "img": f"{LIB}/city_daughter_in_law_32.png",
        "audio": f"{VOICE}/r05_young_female.mp3",
        "desc": "a 32-year-old Chinese woman with shoulder-length straight black hair, wearing a cream knit "
                "sweater and a canvas tote bag on her shoulder, brisk and self-satisfied",
        "voice": "a YOUNG woman's voice — clear, quick and slightly condescending",
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
    "RIDING RULE: whenever it moves with someone on it, that person is SEATED on the cushion with a hand on the "
    "joystick; NOBODY ever pushes it from behind or stands beside it while it rolls.\n"
)

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    cast_block = (
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned, mirrored or twinned into a second similar figure; no extra "
        "bystanders, no crowd in the foreground): a 65-year-old woman and a 32-year-old woman, both Chinese. They "
        "must look CLEARLY DIFFERENT at all times — different age, face shape, hairstyle and clothing colour "
        "(DARK NAVY MANDARIN-COLLAR JACKET AND GREY BUN versus CREAM KNIT SWEATER AND SHOULDER-LENGTH STRAIGHT "
        "HAIR); never the same face, hair or outfit.\n"
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


SCENE = ("the entrance of a busy morning food market in a Chinese residential neighbourhood, with vegetable "
         "stalls and plastic crates along both sides, a few shopping bags on the ground and shoppers moving in "
         "the far background, soft overcast morning light")

SCRIPTS = [
    # ─────────── 段1《自己走路》= 开场双钩子：当众羞辱 + 隐藏身份者现身（第1层护短）───────────
    {
        "uid": "S31_1_zijizou",
        "cast": ["daughter_in_law", "granny"],
        "soundscape": (
            "Busy morning food-market room tone: distant chatter, vegetables being moved and light traffic; clear "
            "natural voices and a soft electric motor hum. No music."
        ),
        "extra_tail": (
            "The wheelchair comes to the grandmother ON ITS OWN — NOBODY touches, pushes or reaches for it while "
            "it moves; both of the grandmother's hands stay at her sides until it has stopped right at her feet. "
            "Emotional beats escalate shot by shot: mild criticism, pitying condescension, astonishment."
        ),
        "shots": [
            {"desc": "COLD OPEN: a tight close-up of the younger woman's eyes giving the grandmother a quick "
                     "head-to-toe look (half a second), then cut wide to the market entrance: the younger woman "
                     "stands with her arms folded, chin lifted, frowning down at the grandmother's legs and "
                     "speaking; the grandmother stands straight and relaxed with both hands at her sides and "
                     "answers her calmly. The camera pushes in slightly.",
             "lines": [("daughter_in_law", "妈，您自己走，人家说我们不孝。"), ("granny", "我走两步挺好。")]},
            {"desc": "The younger woman pushes a battered old shopping trolley forward toward the grandmother with "
                     "one hand, palm open, in a pitying gesture; the grandmother lifts one flat palm to refuse and "
                     "straightens her back, eyes level and steady. The camera glides gently sideways.",
             "lines": [("daughter_in_law", "这旧推车拿去，总比走路强。"), ("granny", "我不用那个推车。")]},
            {"desc": "The younger woman spreads both hands and looks around the market entrance with a mocking "
                     "smile, searching; the grandmother raises her eyes calmly to look straight ahead — and the "
                     "silver-grey wheelchair ROLLS INTO FRAME ON ITS OWN from the background, its wheels turning "
                     "with NOBODY touching or pushing it, and it comes to a smooth stop right at the grandmother's "
                     "feet. Nobody reaches for it. The camera tracks slowly sideways following the wheelchair in.",
             "lines": [("daughter_in_law", "您有车？您的车在哪儿呢？"), ("granny", "它来接我了。")]},
            {"desc": "The younger woman's eyes go wide and her mouth drops open as she stares at the wheelchair "
                     "that just parked itself; the grandmother pats the wheelchair's cushion twice with her flat "
                     "hand and speaks to her, unbothered. The camera pulls back slowly to show both of them.",
             "lines": [("daughter_in_law", "没人碰它，它自个儿会走？"), ("granny", "你上去坐坐。")]},
        ],
    },
    # ─────────── 段2《撑场》= 第2层当众验证 + 第3层菜摊前亮王牌 → 品牌 ───────────
    {
        "uid": "S31_2_chengchang",
        "cast": ["daughter_in_law", "granny"],
        "soundscape": (
            "Same busy morning food-market room tone with distant chatter and light traffic; clear natural voices "
            "and a soft click of the seat taking weight. No music."
        ),
        "extra_tail": (
            "The wheelchair does not sink, flex, wobble or move at all under the younger woman's weight — the "
            "frame and tyres stay completely unchanged. The grandmother never touches the younger woman. "
            "Emotional beats escalate shot by shot: defiance, disbelief, surrender."
        ),
        "shots": [
            {"desc": "The younger woman walks up to the wheelchair and drops herself down heavily onto its cushion "
                     "with her full weight, arms crossed, chin high and defiant; the grandmother stands beside the "
                     "wheelchair, one hand resting on its backrest, watching her with a small smile. The camera "
                     "pushes in slightly.",
             "lines": [("daughter_in_law", "坐就坐，我倒看它能怎样。"), ("granny", "你尽管坐，别客气。")]},
            {"desc": "The younger woman plants both hands on the cushion, rocks her upper body twice and glances "
                     "down at the frame and the four tyres — NOTHING sinks, bends or shifts; her eyes go wide and "
                     "her mouth opens; the grandmother answers her without moving. The camera glides gently "
                     "sideways.",
             "lines": [("daughter_in_law", "哎哟，您这车压不垮吗？"), ("granny", "两百斤坐上去，稳当得很。")]},
            {"desc": "The younger woman stands up out of the wheelchair and runs her fingers along its silver-grey "
                     "frame, frowning as she asks her question; the grandmother hangs two full plastic shopping "
                     "bags of vegetables onto the armrest as she answers, completely at ease. The camera tracks "
                     "sideways keeping BOTH of them and the wheelchair in frame.",
             "lines": [("daughter_in_law", "这车到底得多少钱啊？"), ("granny", "闺女攒半年给我买的。")]},
            {"desc": "The younger woman waves one hand and looks down at her own battered shopping trolley with a "
                     "wry, defeated smile; the grandmother turns her face to the camera and looks straight into "
                     "the lens for the branding line only. The camera pulls back slowly to show both of them.",
             "lines": [("daughter_in_law", "得，我那破推车该扔了。"), ("granny", "爱优护轻便侠。")]},
        ],
    },
]


def main() -> None:
    for s in SCRIPTS:
        prompt = build_prompt(s)
        cast = [CAST_LIB[k] for k in s["cast"]]
        refs = [str(ROOT / c["img"]) for c in cast] + [str(p) for p in REFS_TAIL]
        audios = [str(ROOT / c["audio"]) for c in cast]
        for p in refs + audios:
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
        header = f'<!-- duration="{spec["duration"]}" 语速门禁：纯汉字 65-72（4.5-5.0 字/秒铺满）-->\n'
        (ROOT / f"docs/onetake_check_{s['uid']}.txt").write_text(header + prompt, encoding="utf-8")
        lines = [t for sh in s["shots"] for _, t in sh["lines"]]
        (ROOT / f"docs/onetake_lines_{s['uid']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        cjk = sum(len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines)
        per = [len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines]
        print(f"✓ {s['uid']} → {jp.name}（图 {len(refs)} / 音 {len(audios)} / 纯汉字 {cjk} 单句 {per}）")


if __name__ == "__main__":
    main()
