"""洗脑 10 连（G3 魔性广告）prompt 组装

宝哥 2026-09-26 令：「跑1」→ 先跑 #1《一秒三折》。

结构：宝哥 2026-09-26 定稿的 4 镜 8 句对撞结构 + 洗脑内核（同一记忆点讲 3 遍 + 同一动作演 3 遍）
  镜1 她质疑 → 他【记忆点第1遍】+ 第一次演动作
  镜2 她不信自己上手 → 他【记忆点第2遍】
  镜3 她当场被震到 → 他【记忆点第3遍】+ 第三次演动作
  镜4 她服气收尾 → 他品牌句（面向镜头）

记忆点写法（重要）：check_dialogue 的 R4 把「同一句台词出现多次」判 ERROR，
故记忆点做成**同一关键词的三变体**（一秒钟的事 → 你看，就一秒钟的事。 → 一秒钟的事，折好了。），
听感仍是砸三遍，门禁 0 ERROR。台词源：state/_xinao10_lines.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import prompt_parts as pp  # noqa: E402

LIB = "assets/cast/library"
VOICE = "assets/cast/voice/real"

CAST_LIB = {
    "girl": {
        "short": "girl",
        "img": f"{LIB}/fashion_girl_sporty.png",
        "audio": f"{VOICE}/r05_young_female.mp3",
        "desc": "a 20-year-old Chinese girl with long black hair in a high ponytail with a small bun and "
                "face-framing bangs, wearing a bright white zip-up hooded athletic jacket, cocky and loud",
        "voice": "a YOUNG woman's voice — clear, bright, quick and cocky",
    },
    "grandpa": {
        "short": "grandpa",
        "img": f"{LIB}/fashion_grandpa_cool.png",
        "audio": f"{VOICE}/r12_elder_male.mp3",
        "desc": "a 70-year-old Chinese grandpa with short silver-white hair combed back and a neatly trimmed grey "
                "beard, wearing a dark navy blazer over a crisp white shirt with the top button open, calm and "
                "dignified",
        "voice": "an ELDERLY man's voice — low, deep and unhurried",
    },
}

PROD = ROOT / "assets/products"
REFS_TAIL = [
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]

# 每条：memory_key = 记忆点关键词（洗脑点），spoken_by = 说记忆点的人
SCRIPTS = [
    {
        "uid": "X1_yimiaosanzhe",
        "title": "一秒三折",
        "point": "fold_1s",
        "cast": ["girl", "grandpa"],
        "memory_key": "一秒钟的事",
        "scene": "in front of a flower stall at a busy morning wet market, buckets of fresh cut flowers and green "
                 "buckets on both sides, stalls and awnings behind, a few blurred shoppers far in the background, "
                 "no crowd around the two people",
        "soundscape": "Busy morning market room tone — distant sellers calling, light cart wheels on paving, faint "
                      "birds; clear natural voices close to camera. No music.",
        "extra_tail": "PROP RULE: the only handheld prop is a small bunch of fresh flowers held by the girl — no "
                      "bags, no carts, no other objects. CROWD RULE: only these two people and the one wheelchair "
                      "appear — no bystanders, no shoppers walking through the foreground, no extra faces, and "
                      "nothing ever comes into the picture from outside the frame. STATE-CHANGE RULE: across "
                      "shots 1, 2 and 3 the wheelchair CHANGES FORM exactly three times — once per shot — and "
                      "every change is one complete, uninterrupted, clearly visible transformation lasting about "
                      "one second: shot 1 unfolds it from the folded upright column into the fully open "
                      "wheelchair, shot 2 folds it from the fully open wheelchair back into the folded upright "
                      "column, shot 3 unfolds it again. Each of those shots begins with the wheelchair clearly in "
                      "one state and ends with it clearly in the other — never half-folded, never half-open, "
                      "never part-way in between. An empty gesture on a wheelchair whose shape stays the same "
                      "must never appear in any shot, and the wheels always stay on the ground.",
        "shots": [
            {"desc": "COLD OPEN: an extreme close-up of the FOLDED silver wheelchair standing upright on the "
                     "ground and glinting in the morning light (half a second), then cut wide: at the flower "
                     "stall the girl stands holding a small bunch of fresh flowers in one hand, chin tilted, eyes "
                     "narrowed as she looks the wheelchair up and down in contempt, toes tapping the ground; the "
                     "wheelchair stands beside the grandpa FOLDED, upright on the ground as a compact vertical "
                     "column, and the grandpa takes hold of its frame with one hand and UNFOLDS it in one single "
                     "quick motion — the frame opens straight out and the four wheels settle onto the ground — so "
                     "that it ends FULLY OPEN, standing on all four wheels with the seat and backrest upright; he "
                     "then looks back at her calmly. It ends fully open and STAYS exactly like that for the rest "
                     "of the shot — it never folds back or changes shape again. The camera pushes in slightly.",
             "lines": [("girl", "您这车收起来很费劲吧。"), ("grandpa", "折它，就一秒钟的事。")]},
            {"desc": "The wheelchair now stands FULLY OPEN on all four wheels in front of them. The girl does not "
                     "believe him: she steps in and, with one hand pressing straight down on the seat cushion, "
                     "FOLDS the wheelchair in one single quick motion — the seat drops and the frame collapses — "
                     "so that it ends FOLDED, standing upright on the ground as a compact vertical column; she "
                     "keeps her hand resting on top of the folded frame, frowning in disbelief, while the grandpa "
                     "steps half a pace back, folds his arms and simply watches her, unbothered. It ends folded "
                     "and STAYS exactly like that for the rest of the shot — it never unfolds again or changes "
                     "shape again. The camera glides gently sideways keeping BOTH of them and the wheelchair in "
                     "frame.",
             "lines": [("girl", "我一只手能收起来吗？"), ("grandpa", "你看，就一秒钟的事。")]},
            {"desc": "The wheelchair stands FOLDED on the ground as a neat vertical column; the girl straightens up "
                     "and raises one finger in front of her chest to mark 'one second', eyes wide, mouth open in "
                     "surprise as she speaks; the grandpa then takes hold of the folded frame with one hand and "
                     "UNFOLDS it in one single quick motion — the frame opens straight out and the wheels settle "
                     "onto the ground — so that it ends FULLY OPEN, standing on all four wheels with the seat and "
                     "backrest upright; he rests one hand on the armrest, perfectly relaxed. It ends fully open "
                     "and STAYS exactly like that for the rest of the shot — it never folds back again. The camera "
                     "pushes in slowly on the two of them.",
             "lines": [("girl", "真就一秒，您没骗人！"), ("grandpa", "一秒钟的事，折好了。")]},
            {"desc": "The girl nods, convinced, and turns toward the grandpa as she asks her question; the grandpa "
                     "stands beside the fully opened wheelchair and, for the branding line only, turns his face to the "
                     "camera and looks straight into the lens. The camera pulls back slowly to show both of them "
                     "and the wheelchair.",
             "lines": [("girl", "大爷，这车贵不贵啊？"), ("grandpa", "爱优护轻便侠。")]},
        ],
    },
]

WHEEL = (
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT ELECTRIC wheelchair matching reference images 3, 4 and 5 — "
    "silver-grey frame, black cushion seat, red springs, brand lettering as in the references; its motor hubs, "
    "the distinctive RED shock-absorbing springs and the JOYSTICK on its right armrest stay clearly visible in "
    "every shot. It is never a plain manual wheelchair, never a bicycle, scooter or motorcycle, and never turns "
    "into a different vehicle. When folded it stands upright ON THE GROUND as a compact vertical column on its "
    "own wheels — never laid flat, never in mid-air, never floating.\n"
)


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    cast_block = (
        f"SCENE: {script['scene']}\n"
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned, mirrored or twinned into a second similar figure; no extra "
        "bystanders, no crowd, no passers-by): a 20-year-old young woman and a 70-year-old grandpa. They must look "
        "CLEARLY DIFFERENT at all times — different age, gender, hair colour and hairstyle, clothing colour; never "
        "the same face, hair or outfit.\n"
    )
    for i, c in enumerate(cast):
        cast_block += (
            f"- (S{i + 1}) {c['desc']}, exactly as in reference image {i + 1}. "
            f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n"
        )
    cast_block += (
        "The two voices are clearly DIFFERENT in pitch and age; never swap them.\n"
        + WHEEL
        + f"SPEECH RULE: the phrase \"{script['memory_key']}\" is a deliberately repeated catchphrase — it is "
        "spoken three times across the video in three slightly different wordings (once in shot 1, once in shot 2 "
        "and once in shot 3), always by (S2) calmly and confidently, always with the same measured delivery. "
        "EVERY OTHER LINE IS SPOKEN EXACTLY ONCE: no line is ever repeated, doubled, echoed or paraphrased.\n"
        "SPEAKER RULE: exactly ONE person speaks at a time and only that person's lips move while their line is "
        "being spoken, with the voice coming from that person's mouth; everybody who is not speaking keeps their "
        "lips completely closed and still — they never open their mouth, never mouth any word and are never the "
        "source of any voice.\n"
    )

    shots = ""
    for i, shot in enumerate(script["shots"]):
        seg = f"[Shot {i + 1}, {SHOT_TIMES[i]}] {shot['desc']} "
        for j, (who, text) in enumerate(shot["lines"]):
            idx = script["cast"].index(who) + 1
            verb = "says" if j == 0 else "replies"
            seg += f"(S{idx}) the {CAST_LIB[who]['short']} {verb}: <d>[Chinese] {text}</d> "
        names = [(script["cast"].index(w) + 1, CAST_LIB[w]["short"]) for w, _ in shot["lines"]]
        order = " then ".join(f"(S{i}) the {s}" for i, s in names)
        seg += (
            f"SPEAKER LOCK — {order}; only the speaker's lips move and the voice comes from that mouth, whoever "
            "is silent keeps their lips closed and still. Hard cut. "
        )
        shots += seg + "\n\n"

    return pp.compose(
        shots=shots,
        cast=cast_block,
        soundscape=script["soundscape"],
        extra_tail=script["extra_tail"],
        cold_open=False,          # 镜 1 自带 cold open 特写，去掉全局重复段（H3 prompt 上限 10000 字符）
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", default="", help="只生成指定条（默认全部）")
    ap.add_argument("--gate", action="store_true", help="生成后跑 check_dialogue.mjs 门禁")
    args = ap.parse_args()

    import subprocess

    for s in SCRIPTS:
        if args.uid and args.uid != s["uid"]:
            continue
        prompt = f'<!-- duration="15" -->\n' + build_prompt(s)
        cast = [CAST_LIB[k] for k in s["cast"]]
        refs = [str(ROOT / c["img"]) for c in cast] + [str(p) for p in REFS_TAIL]
        audios = [str(ROOT / c["audio"]) for c in cast]
        missing = [p for p in refs + audios if not Path(p).exists()]
        spec = {
            "job_uid": s["uid"],
            "title": s["title"],
            "template_id": "manual", "template_name": "manual", "mode": "manual",
            "workflow": "minimax_h3_image_audio_to_video_v2_15s",
            "fallback_workflows": ["minimax_h3_zm_u08", "minimax_h3_zm_u24"],
            "duration": 15,
            "resolution": "768p竖",
            "ref_images": refs,
            "ref_audios": audios,
            "prompt": prompt,
            "lines_meta": [],
        }
        jp = ROOT / f"state/onetake_prompt_job_{s['uid']}.json"
        jp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        cp = ROOT / f"docs/onetake_check_{s['uid']}.txt"
        cp.write_text(prompt, encoding="utf-8")
        lines = [t for sh in s["shots"] for _, t in sh["lines"]]
        (ROOT / f"docs/onetake_lines_{s['uid']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        cjk = sum(len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines)
        per = [len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines]
        flag = "  ⚠️ 缺文件: " + ", ".join(missing) if missing else ""
        print(f"✓ {s['uid']} → {jp.name}（图 {len(refs)} / 音 {len(audios)} / 纯汉字 {cjk} 单句 {per}）{flag}")

        if args.gate:
            r = subprocess.run(["node", "tools/check_dialogue.mjs", str(cp.relative_to(ROOT))],
                               cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
            print("   门禁：", r.stdout.strip().splitlines()[-2].strip() if r.stdout.strip() else r.stderr.strip())


if __name__ == "__main__":
    main()
