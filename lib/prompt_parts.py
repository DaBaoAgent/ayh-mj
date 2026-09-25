"""标准 Prompt 片段库 — 供所有 prep 脚本复用（2026-09-25 宝哥令）

光线质感词统一：所有出片 prompt 必须拼入 CAMERA / REALISM 段
脚本规范 v2：钩子三选一 / 0.5s 冲击开场 / 双反转（见 docs/脚本规范v2）
"""
from __future__ import annotations

# ── 节奏（明快档，宝哥 2026-09-24 定）──
PACE = (
    "Pacing is tight and bouncy; everyone speaks at a natural, brisk conversational pace. "
    "The first line starts within the first quarter second, every line begins immediately after the previous "
    "line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause "
    "exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing "
    "silence. The camera is always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — "
    "never static. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it."
)

# ── 光线质感词统一（真实感三连，2026-09-25 新增）──
REALISM = (
    "Shot like real documentary footage: natural available light with soft realistic shadows, lifelike skin "
    "texture with visible pores and fine lines, natural hair detail, true-to-life colors, subtle handheld "
    "micro-movement feel, shallow depth of field like an 85mm lens at f/2, photorealistic and candid — "
    "no plastic skin, no over-smoothing, no studio sheen."
)

# ── 开场冲击（0.5s 大特写，2026-09-25 新增）──
COLD_OPEN = (
    "The video opens on a striking extreme close-up (an expressive face, a pointing hand, or the hero product "
    "glinting) filling the frame for the first half second, then cuts into the main action — the first spoken "
    "line lands within the first quarter second from the very start."
)

# ── 常量尾巴 ──
HARD_TAIL = (
    "render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform "
    "logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it "
    "appears in the reference images; every person's appearance, hair and clothing must stay exactly consistent "
    "with the reference images throughout all shots; the shots are joined by immediate hard cuts with no fades "
    "or dissolves."
)


def compose(shots: str, cast: str, soundscape: str = "", extra_tail: str = "", cold_open: bool = True) -> str:
    """标准拼装：开场 + CAST + 镜头 + 收尾约束"""
    parts = [f"integrated_multimodal_description: Live-action fun commercial in vertical framing. {PACE} {REALISM}"]
    if cold_open:
        parts.append(COLD_OPEN)
    if cast:
        parts.append(cast)
    parts.append(shots)
    if soundscape:
        parts.append(f"overall_soundscape: {soundscape}")
    parts.append("non_diegetic_music: N/A")
    parts.append(f"Hard constraints: {HARD_TAIL}" + (f" {extra_tail}" if extra_tail else ""))
    return "\n\n".join(parts)
