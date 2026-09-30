"""H1《英雄对决》15s spec 组装 — 三件套第二个全流程实例（2026-09-26/27）

题材：泛化「英雄对决」——**不写任何专有名词**（Batman/Superman/DC 等一律不出现），
形象走风格泛化（黑衣斗篷侠 vs 红蓝紧身衣侠），零版权风险。

三件套落地位置：
  · LIRA      → `assets/cast/scene/{dark_knight,blue_hero}_rooftop_night_H1.png`（全新角色，无 ref，纯文字生成）
  · CINEDANCE → `pp.compose(cinedance=True)` + `hg.shot_block()` 逐镜 FOV/机位/首帧占位/光锁
  · ACTING    → `hg.acting_block(eye=False)`；主档案 `assets/cast/acting/{dark_knight,blue_hero}.md`
                的本片场景改写版 `scene_H1_*.md`

台词：docs/onetake_lines_H1_hero.txt（70 纯汉字，撞车检查 0 拦截）
结构：4 镜 8 句对撞 —— 互报家门 → 互怼本钱 → 摆架势 → **喜剧反转（堵车）**

⚠️ 与软广线的差异：本片**不带产品**（无 WHEEL 段、无产品参考图），是题材迁移验证片。
   留出的额度换成了 ACTING 表演层的完整度。

用法：
    PY=.venv/Scripts/python.exe
    $PY tools/prep_h1_hero.py --gate
    $PY tools/prep_h1_hero.py --dry
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import hellgrind as hg  # noqa: E402
from lib import prompt_parts as pp  # noqa: E402

UID = "H1_hero"
TITLE = "英雄对决"
SCENE_KEY = "H1"

VOICE = "assets/cast/voice/real"
SCENE_DIR = "assets/cast/scene"

# 音色：两男声必须 f0 差 ≥60Hz（r09 成年男 145.5 / r03 青年男 225.4 → 差 79.9 ✅）
CAST = {
    "dk": dict(
        short="dark knight",
        img=f"{SCENE_DIR}/dark_knight_rooftop_night_H1.png",
        audio=f"{VOICE}/r09_adult_male.mp3",
        desc="the DARK KNIGHT, a heavy-set 40-year-old man with a square jaw and a faint stubble shadow, "
             "wearing a matte-black segmented tactical armoured suit with a long charcoal-grey cape and a "
             "black cowl covering the top half of his face with two short pointed ears, so that only his "
             "jaw, mouth and eyes are visible; heavy black armoured boots",
        voice="a LOW, GRAVELLY man's voice pushed from the chest — short sentences bitten off at the end, "
              "deliberately slowed and flattened",
    ),
    "bh": dict(
        short="blue hero",
        img=f"{SCENE_DIR}/blue_hero_rooftop_night_H1.png",
        audio=f"{VOICE}/r03_young_male.mp3",
        desc="the BLUE HERO, a tall athletic clean-shaven man of 35 with short dark hair brushed back, "
             "wearing a deep-blue fitted suit with a high silver collar, a red cape falling to his knees, "
             "red knee-high boots and a red belt. His chest is PLAIN UNBROKEN DEEP-BLUE FABRIC — there is "
             "NO emblem, NO badge, NO logo, NO shield, NO letter, NO symbol and NO marking of any kind "
             "anywhere on the suit or the cape, front or back; a completely unadorned costume; no mask, "
             "no glasses",
        voice="a WARM CLEAR mid-low man's voice — slow and even, every sentence landing softly, lighter the "
              "more serious the moment",
    ),
}

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]
KEYS = ["dk", "bh"]

SHOTS = [
    dict(
        fov="44 degrees", camera="camera 3 metres away at chest height, drifting slowly sideways",
        occupancy="both men centred and facing each other about four metres apart, the city skyline behind them",
        light="cool blue night light from above with a faint warm glow rising from the street below, the "
              "camera on the shaded side, both faces evenly exposed",
        desc="On a concrete rooftop at night the DARK KNIGHT and the BLUE HERO stand facing each other about "
             "four metres apart, both completely still — the caped black figure with his arms heavy at his "
             "sides and his jaw set, the blue-and-red figure standing open and easy with his hands hanging "
             "loose. Neither moves toward the other; only their eyes travel. The camera drifts slowly sideways "
             "keeping both of them in frame.",
        lines=[("dk", "你就是那个会飞的外星人？"), ("bh", "你就是那个穿斗篷的凡人？")],
        beats="the dark knight shifts his jaw once to one side before he speaks; the blue hero blinks slowly "
              "and his mouth lifts faintly",
    ),
    dict(
        fov="40 degrees", camera="camera 1.8 metres away, a slow half-circle around the two of them",
        occupancy="the two men fill the frame head to waist, the dark figure low-left and the blue figure high-right",
        desc="Closer now: the DARK KNIGHT has not moved his feet at all and answers without raising his voice, "
             "his narrow eyes tracking the other man's hands and feet; the BLUE HERO takes one small audible "
             "breath before he replies, still with both hands open and away from his body. The camera slides "
             "in a slow half-circle around the pair, keeping both faces visible.",
        lines=[("dk", "我靠的从来都是脑子。"), ("bh", "我靠的就是这双拳头。")],
        beats="the dark knight's fingers close slowly into a fist and then deliberately flatten; the blue hero's "
              "calm face flickers with a flash of real delight that he smooths away",
    ),
    dict(
        fov="42 degrees", camera="camera 2.2 metres away, a gentle push-in",
        occupancy="both men centred, each turned a quarter toward the other, the rooftop parapet behind",
        desc="The DARK KNIGHT turns his shoulders a quarter toward the other man and settles his weight low, "
             "one arm coming slightly away from his body — a combat stance held without a single step "
             "forward; the BLUE HERO simply shifts his weight from one foot to the other, keeps his hands "
             "open and low, and lets a small smile show. The camera pushes in gently on the two of them.",
        lines=[("dk", "那我先让你三招。"), ("bh", "你确定？我可不客气。")],
        beats="the dark knight's stance sets; the blue hero's smile widens by a fraction and his chin drops",
    ),
    dict(
        fov="38 degrees", camera="camera 2.4 metres away, pulling back slowly",
        occupancy="both men centred and fully visible, the lit skyline between them",
        desc="The DARK KNIGHT suddenly straightens up out of his stance and lifts one flat hand between them, "
             "asking for a pause, his jaw working to one side as he thinks of something — and the BLUE HERO "
             "stops, lets his shoulders drop, and answers with a small shrug, both of them now completely "
             "relaxed and standing almost companionably under the night sky. The camera pulls back slowly and "
             "holds the wide two-shot to the end of the video.",
        lines=[("dk", "等等，你飞过来要多久？"), ("bh", "三个小时，堵车。")],
        beats="the dark knight's combat stillness breaks into an ordinary gesture; the blue hero's shrug turns "
              "the whole scene domestic — the reversal plays entirely in the body, not the words",
    ),
]

EXTRA_TAIL = (
    "PROP RULE: no props at all — no weapons, no vehicles, no handheld objects, and neither man ever throws "
    "a punch or makes contact with the other; this is a standoff of two people talking and reacting, never a "
    "fight scene. COSTUME RULE: the cowl, cape, armour, belt and boots look exactly as in the reference "
    "images and never change, come off, or turn into other clothing. The blue hero's chest stays PLAIN AND "
    "UNADORNED at every moment of the video — no emblem, no badge, no shield, no letter and no symbol ever "
    "appears on his chest or cape in any shot."
)

SOUNDSCAPE = (
    "Cold night wind across an open rooftop, a faint distant hum of city traffic far below, one single flap "
    "of cloth when a cape shifts; clear natural voices close to camera. No music."
)


def build_prompt() -> str:
    cast = [CAST[k] for k in KEYS]
    n = len(cast)
    cast_block = (
        "SCENE: the concrete rooftop of a city building at night — low parapet walls, a water tank silhouette "
        "and ventilation ducts behind, the distant city skyline as heavily blurred lit windows; the light "
        "never changes.\n"
        f"CAST (STRICTLY BIND — exactly {n} people; each appears EXACTLY ONCE per shot, never duplicated, "
        "cloned, mirrored or twinned into a second similar figure; no other person, no crowd, no bystanders, "
        "and nothing ever comes into the picture from outside the frame): two very different men — one short "
        "and heavy in black armour with a cowl and cape, one tall and athletic in blue with a red cape. They "
        "must look CLEARLY DIFFERENT at all times; never the same face, build or outfit.\n"
    )
    for i, c in enumerate(cast):
        cast_block += (f"- (S{i + 1}) {c['desc']}, exactly as in reference image {i + 1}. "
                       f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n")
    cast_block += (
        "The two voices are clearly DIFFERENT in pitch and weight; never swap them.\n"
        "STAGING RULE: they stand at a fixed distance and never close it — no walking toward each other, no "
        "grabbing, no impact, no choreography. All conflict is carried by stillness, posture, the jaw and the "
        "eyes.\n"
        "SPEAKER RULE: exactly ONE person speaks at a time and only that person's lips move while their line "
        "is spoken, the voice coming from that mouth; everybody not speaking keeps their lips completely "
        "closed and still, never opens their mouth and is never the source of any voice. EVERY LINE IS SPOKEN "
        "EXACTLY ONCE — never repeated, doubled, echoed or paraphrased."
    )

    acting_lines = []
    for i, k in enumerate(KEYS):
        p = hg.ACTING_DIR / f"scene_{SCENE_KEY}_{k}.md"
        if p.exists():
            acting_lines.append(f"As (S{i + 1}) {p.read_text(encoding='utf-8').strip()}")
    acting = hg.acting_block(acting_lines, eye=False)

    shots = ""
    for i, s in enumerate(SHOTS):
        seg = hg.shot_block(i + 1, SHOT_TIMES[i], s["desc"], fov_deg=s["fov"], camera=s["camera"],
                            occupancy=s["occupancy"], light=s["light"] if i == 0 else "")
        for j, (who, text) in enumerate(s["lines"]):
            idx = KEYS.index(who) + 1
            seg += f" (S{idx}) the {CAST[who]['short']} {'says' if j == 0 else 'replies'}: <d>[Chinese] {text}</d>"
        order = " then ".join(f"(S{KEYS.index(w) + 1}) the {CAST[w]['short']}" for w, _ in s["lines"])
        seg += f" SPEAKER LOCK — {order} only."
        if s.get("beats"):
            seg += f" BEATS — {s['beats']}."
        seg += " Hard cut."
        shots += seg + "\n\n"

    return pp.compose(
        shots=shots, cast=cast_block, soundscape=SOUNDSCAPE, extra_tail=EXTRA_TAIL,
        cold_open=False, cinedance=True, acting=acting,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    hg.ensure_dirs()
    prompt = '<!-- duration="15" -->\n' + build_prompt()
    refs = [str(ROOT / CAST[k]["img"]) for k in KEYS]
    audios = [str(ROOT / CAST[k]["audio"]) for k in KEYS]
    missing = [Path(p).name for p in refs + audios if not Path(p).exists()]
    plen = len(prompt)
    print(f"📝 prompt {plen} 字符（上限 10000 / 安全线 9800）→ {'✅ 在安全线内' if plen <= 9800 else '❌ 超限'}")
    print(f"   参考图 {len(refs)} 张 / 音色 {len(audios)} 条" + (f"  ⚠️ 缺：{missing}" if missing else "  ✓ 文件齐全"))
    if a.dry:
        print("\n" + prompt[:1400] + "\n...[截断]")
        return 0

    spec = {
        "job_uid": UID, "title": TITLE,
        "template_id": "manual", "template_name": "manual", "mode": "manual",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_zm_u08", "minimax_h3_zm_u24"],
        "duration": 15, "resolution": "768p竖",
        "ref_images": refs, "ref_audios": audios,
        "prompt": prompt, "lines_meta": [],
    }
    jp = ROOT / f"state/onetake_prompt_job_{UID}.json"
    jp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    cp = ROOT / f"docs/onetake_check_{UID}.txt"
    cp.write_text(prompt, encoding="utf-8")
    lines = [t for s in SHOTS for _, t in s["lines"]]
    (ROOT / f"docs/onetake_lines_{UID}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cjk = sum(len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines)
    per = [len(re.sub(r"[^\u4e00-\u9fff]", "", t)) for t in lines]
    print(f"✓ {jp.name} ｜ 纯汉字 {cjk} ｜ 逐句 {per}")

    if a.gate:
        r = subprocess.run(["node", "tools/check_dialogue.mjs", str(cp.relative_to(ROOT))],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        out = (r.stdout or "").strip()
        print("\n=== 门禁 check_dialogue.mjs ===")
        print(out[-1400:] if out else (r.stderr or "").strip()[-800:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
