"""G5《景点打卡》15s spec 组装 — Higgsfield 三件套首个全流程实例（2026-09-26）

三件套在这条片里的落地位置：
  · LIRA      → 参考图 `assets/cast/scene/{son,elder}_jingdian_G5.png`（同人换场景，tools/gen_cast_scene.py 出）
  · CINEDANCE → `pp.compose(cinedance=True)` 电影语言总纲 + `hg.shot_block()` 逐镜 FOV/机位/首帧占位/光锁
  · ACTING    → `hg.acting_block(eye=False)` 拼入表演层；主档案 `assets/cast/acting/{elder,son}.md`，
                本片用其场景改写版 `scene_G5_*.md`（ACTING §8：改写而非粘贴）

四池组合：核心卡司组 / 卖点 load_100 承重100kg / 角度 B11 景点打卡 / 片型 G5 情感故事
台词：docs/onetake_lines_G5_jingdian.txt（70 纯汉字，撞车检查 0 拦截）

⚠️ 长度纪律：H3 prompt 硬上限 10000 字符（安全线 9800）。本脚本已按压缩五招裁剪；
   任何新增约束都要先量 `len(prompt)`，超了就按 docs/执行标准 2.10b 的招式再压。

用法：
    PY=.venv/Scripts/python.exe
    $PY tools/prep_g5_jingdian.py --gate      # 组装 + 跑门禁
    $PY tools/prep_g5_jingdian.py --dry       # 只看长度与前 1500 字符
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
from lib import prompt_parts as pp  # noqa: E402
from lib import hellgrind as hg  # noqa: E402

UID = "G5_jingdian"
TITLE = "景点打卡"
SCENE_KEY = "G5"

VOICE = "assets/cast/voice/real"
SCENE_DIR = "assets/cast/scene"

CAST = {
    "son": dict(
        short="son",
        img=f"{SCENE_DIR}/son_jingdian_G5.png",
        audio=f"{VOICE}/r03_young_male.mp3",
        desc="the SON, a 48-year-old Chinese man, short black hair greying at the temples, long rectangular "
             "face, tired dark brown eyes, salt-and-pepper stubble, open black jacket over a dark grey "
             "t-shirt and dark blue jeans",
        voice="a YOUNGER man's voice — light, slightly nasal, fast clipped sentences turning up into questions",
    ),
    "elder": dict(
        short="grandpa",
        img=f"{SCENE_DIR}/elder_jingdian_G5.png",
        audio=f"{VOICE}/r12_elder_male.mp3",
        desc="the GRANDPA, a 70-year-old Chinese man, short neatly combed silver-grey hair, square-round face, "
             "deep-set eyes with crow's feet, open dark navy zip jacket over a grey knit sweater, black "
             "trousers and black slip-on shoes",
        voice="an ELDERLY man's voice — low, gravelly, unhurried, going quieter as things get serious",
    ),
}

PROD = ROOT / "assets/products"
REFS_TAIL = [PROD / "折叠-无阴影.png", PROD / "正侧-3-无阴影.png", PROD / "45度-加水杯-无阴影.png"]
SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]
KEYS = ["son", "elder"]

SHOTS = [
    dict(
        fov="42 degrees", camera="camera 2.5 metres away at chest height, drifting slowly sideways",
        occupancy="both men fill the middle band, the folded wheelchair low-centre between them",
        light="soft overcast daylight from the upper left, camera on the shaded side",
        desc="At the entrance of a scenic walkway the SON has stopped and half-turned back, one arm raised to "
             "block the way, trying to talk his father out of the walk; the GRANDPA stands beside the small "
             "silver lightweight electric wheelchair — FOLDED, standing upright on the ground as a compact "
             "vertical column — and flicks the arm away with a dismissive wave, chin lifted, unbothered.",
        lines=[("son", "爸，这景点走下来得两万步呢。"), ("elder", "怕啥，我又不是走不动。")],
        beats="the son leans in and presses; the grandpa's flicked hand dismisses it and his chin comes up",
    ),
    dict(
        fov="46 degrees", camera="camera 2 metres away, a slow sideways sweep",
        occupancy="the son bent over at frame-left, the grandpa seated on the open wheelchair at frame-right",
        desc="Further along the walkway the SON is bent over with his hands on his knees, wiping his forehead "
             "with the back of one wrist, out of breath; the GRANDPA glides past him seated on the wheelchair, "
             "now FULLY OPEN on all four wheels, one hand on the control, sitting upright and relaxed, looking "
             "back over his shoulder with an easy grin.",
        lines=[("son", "不行了，我腿都软了。"), ("elder", "你这才走了多远啊。")],
        beats="the son's careful face collapses into breathlessness; the grandpa's grin widens as he looks back",
    ),
    dict(
        fov="40 degrees", camera="camera 1.8 metres away, a gentle push-in",
        occupancy="the two men centred, the open wheelchair filling the lower half between them",
        desc="The SON points at the wheelchair with an openly doubtful look, one eyebrow up; the GRANDPA slaps "
             "the black seat cushion twice with an open palm, then rests his hand flat on it and nods, "
             "inviting him to sit; the wheelchair stands FULLY OPEN on all four wheels, its silver-grey frame, "
             "red springs and joystick clearly visible.",
        lines=[("son", "这车真能扛得住我？"), ("elder", "你放心，它载得动你。")],
        beats="the son's doubt turns into a testing squint; the grandpa answers without a flicker of doubt",
    ),
    dict(
        fov="38 degrees", camera="camera 2.2 metres away, pulling back slowly",
        occupancy="the son seated on the wheelchair centre-frame, the grandpa standing beside it, both fully visible",
        desc="The SON is now SEATED on the wheelchair, both feet flat on the footplates, both hands on the "
             "armrests, testing it with a small bounce of surprise and looking at his father with something "
             "softer in his face; the GRANDPA stands beside him and, for the branding line only, turns his "
             "face to the camera and looks straight into the lens.",
        lines=[("son", "爸，你比我这年轻人还利索。"), ("elder", "爱优护轻便侠。")],
        beats="the son's guard drops and his face softens; the grandpa's wry half-smile turns warm for one beat",
    ),
]

WHEEL = (
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT ELECTRIC wheelchair matching reference images 3, 4 and 5 — "
    "silver-grey frame, black cushion seat, red springs, brand lettering as in the references; its motor hubs, "
    "the RED shock-absorbing springs and the JOYSTICK stay clearly visible in every shot. It is never a plain "
    "manual wheelchair, never a bicycle or scooter. Folded, it stands upright ON THE GROUND as a compact "
    "vertical column — never laid flat, never floating. It is strong enough that an adult man sits on it "
    "without flexing, tipping or breaking."
)

EXTRA_TAIL = (
    "PROP RULE: the only prop is the one wheelchair — no bags, no bottles, no other vehicles."
)

SOUNDSCAPE = (
    "Autumn scenic-spot room tone — light wind, distant birdsong, faint far-off voices, the low hum of the "
    "wheelchair motor; clear natural voices close to camera. No music."
)


def build_prompt() -> str:
    cast = [CAST[k] for k in KEYS]
    n = len(cast)
    cast_block = (
        "SCENE: a stone-paved walkway at a Chinese scenic tourist spot in autumn — low stone balustrade, "
        "traditional grey-tiled eaves behind, heavily blurred tourists far in the background; the light never "
        "changes.\n"
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, cloned, mirrored or twinned into a second similar figure; no extra "
        "bystanders, no crowd, and nothing ever comes into the picture from outside the frame): a 48-year-old "
        "son and a 70-year-old grandpa who must look CLEARLY DIFFERENT at all times — different age, hair, face "
        "and clothing colour; never the same face or outfit.\n"
    )
    for i, c in enumerate(cast):
        cast_block += (f"- (S{i + 1}) {c['desc']}, exactly as in reference image {i + 1}. "
                       f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n")
    cast_block += (
        "The two voices are clearly DIFFERENT in pitch and age; never swap them.\n"
        + WHEEL + "\n"
        "SPEAKER RULE: exactly ONE person speaks at a time and only that person's lips move while their line "
        "is spoken, the voice coming from that mouth; everybody not speaking keeps their lips completely closed "
        "and still, never opens their mouth and is never the source of any voice. EVERY LINE IS SPOKEN EXACTLY "
        "ONCE — never repeated, doubled, echoed or paraphrased."
    )

    # ACTING 场景改写版 → 表演层
    acting_lines = []
    for i, k in enumerate(KEYS):
        p = hg.ACTING_DIR / f"scene_{SCENE_KEY}_{k}.md"
        if p.exists():
            acting_lines.append(f"As (S{i + 1}) {p.read_text(encoding='utf-8').strip()}")
    acting = hg.acting_block(acting_lines, eye=False)   # 眼神细节已在场景改写版内，避免重复占额度

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
        cold_open=False,      # 压缩招①：镜 1 描述自带入场，去掉全局重复段
        cinedance=True,       # ← CINEDANCE
        acting=acting,        # ← ACTING
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true", help="组装后跑 check_dialogue.mjs 门禁")
    ap.add_argument("--dry", action="store_true", help="只打印不落盘")
    a = ap.parse_args()

    hg.ensure_dirs()
    prompt = '<!-- duration="15" -->\n' + build_prompt()

    refs = [str(ROOT / CAST[k]["img"]) for k in KEYS] + [str(p) for p in REFS_TAIL]
    audios = [str(ROOT / CAST[k]["audio"]) for k in KEYS]
    missing = [Path(p).name for p in refs + audios if not Path(p).exists()]
    plen = len(prompt)
    print(f"📝 prompt {plen} 字符（上限 10000 / 安全线 9800）→ {'✅ 在安全线内' if plen <= 9800 else '❌ 超限，需继续压缩'}")
    print(f"   参考图 {len(refs)} 张 / 音色 {len(audios)} 条" + (f"  ⚠️ 缺：{missing}" if missing else "  ✓ 文件齐全"))
    if a.dry:
        print("\n" + prompt[:1500] + "\n...[截断]")
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
