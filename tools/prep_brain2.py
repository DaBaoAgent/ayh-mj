"""脑洞10连第二批 — prompt 组装（10 条 → 10 个 spec）

模板继承 T20 v3 成功版：style 段 + CAST 绑定 + WHEELCHAIR + 4 镜 + 约束
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from brain2_data import CAST_LIB, SCRIPTS  # noqa: E402

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
    "always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Shot like "
    "real documentary footage: natural available light with soft realistic shadows, lifelike skin texture with "
    "visible pores and fine lines, natural hair detail, true-to-life colors, shallow depth of field like an 85mm "
    "lens at f/2, photorealistic and candid — no plastic skin, no over-smoothing.\n\n"
)

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    lines = [STYLE]
    lines.append(
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated; no extra bystanders): both Chinese, speaking standard Mandarin; their clothing "
        "colors are clearly DIFFERENT and never swapped.\n"
    )
    roles = ["the main character", "the other person"]
    for i, c in enumerate(cast):
        lines.append(
            f"- ({'S' + str(i + 1)}) {c['desc']}, exactly as in reference image {i + 1}. "
            f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n"
        )
    lines.append(
        "The two voices are clearly DIFFERENT in pitch and age; never swap them.\n"
        "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching reference images 3, 4 and 5: "
        "silver-grey frame, black cushion seat, red springs, brand lettering as in references). The SAME single "
        "wheelchair in every shot.\n\n"
    )
    # 镜头
    for i, shot in enumerate(script["shots"]):
        segs = [f"[Shot {i + 1}, {SHOT_TIMES[i]}] {shot['desc']} "]
        for j, (who, text) in enumerate(shot["lines"]):
            idx = script["cast"].index(who) + 1
            verb = "says" if j == 0 else "replies"
            segs.append(f"(S{idx}) {verb}: <d>[Chinese] {text}</d> ")
        segs.append("ONLY the speaker's mouth moves; the other person's lips stay closed. ")
        if i < 3:
            segs.append("Hard cut. ")
        lines.append("".join(segs) + "\n\n")
    lines.append(
        f"Scene: {script['scene']}. Only these people speak, taking turns with no overlap, in exactly this order. "
        "All dialogue spoken verbatim, no extra words, no omissions, no repeated lines. No on-screen text; dialogue "
        "is audio only.\n\n"
    )
    lines.append(
        "overall_soundscape: Ambient outdoor/indoor room tone fitting the scene, clear natural voices.\n\n"
        "non_diegetic_music: N/A\n\n"
        "Hard constraints: exactly ONE wheelchair, always the small silver-grey lightweight one; each person appears "
        "exactly once per shot and is never duplicated; the two people never swap clothes, faces, voices or roles; "
        "no extra people; no background music; render no watermarks, subtitles or text anywhere; looks stay exactly "
        "consistent with the reference images; hard cuts only, no fades."
    )
    return "".join(lines)


def main() -> None:
    for s in SCRIPTS:
        prompt = build_prompt(s)
        cast = [CAST_LIB[k] for k in s["cast"]]
        refs = [str(ROOT / c["img"]) for c in cast] + [str(p) for p in REFS_TAIL]
        audios = [str(ROOT / c["audio"]) for c in cast]
        spec = {
            "job_uid": f"job_{s['uid']}",
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
        print(f"✓ {s['title']:8s} → {jp.name}")

    print(f"\n共 {len(SCRIPTS)} 条 spec 已生成")


if __name__ == "__main__":
    main()
