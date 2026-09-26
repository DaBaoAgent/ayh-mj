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
    "never static. Whenever anyone speaks, their face stays clearly visible and is never hidden, cropped or "
    "turned away out of sight."
)

# ── 视线规则（宝哥 2026-09-25 令：对话时脸对着对方，只有最后报品牌那句才面对镜头）──
GAZE = (
    "GAZE RULE: while the two people talk to each other, each speaker turns their face TOWARD THE OTHER PERSON — "
    "a natural three-quarter view from the camera, never a straight-to-camera stare — and both people stay clearly "
    "visible in frame in every shot, nobody hidden, cropped or out of frame. ONLY in the FINAL branding line (the "
    "one line that names the brand) does the speaker turn to face the camera directly and look straight into the lens."
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


def compose(shots: str, cast: str, soundscape: str = "", extra_tail: str = "", cold_open: bool = True,
            acting: str = "", cinedance: bool = False) -> str:
    """标准拼装：电影语言 + 开场 + CAST + 表演层 + 镜头 + 收尾约束

    acting   : 表演层文本（lib/hellgrind.acting_block 的产出，ACTING 技能）——留空则不带，向后兼容
    cinedance: True 则拼入 CINEDANCE 电影语言总纲（镜头/首帧/光锁/物理锁）
    """
    parts = [f"integrated_multimodal_description: Live-action fun commercial in vertical framing. "]
    if cinedance:
        from lib.hellgrind import CINEDANCE_CONSTANTS
        parts.append(CINEDANCE_CONSTANTS + " ")
    parts.append(f"{PACE} {REALISM} {GAZE}")
    if cold_open:
        parts.append(COLD_OPEN)
    if cast:
        parts.append(cast)
    if acting:
        parts.append(acting)
    parts.append(shots)
    if soundscape:
        parts.append(f"overall_soundscape: {soundscape}")
    parts.append("non_diegetic_music: N/A")
    parts.append(f"Hard constraints: {HARD_TAIL}" + (f" {extra_tail}" if extra_tail else ""))
    return "\n\n".join(parts)


# ── 说话人锁定（宝哥 2026-09-26 返工令：全片每镜必写）──
def speaker_lock(speakers: str, others: str = "") -> str:
    """每镜点名「只有谁说话」，其余人闭嘴。

    修的两类实测事故：① 台词是主角的、画面里别人在动嘴；② 两个店员/两个人同时动嘴。
    用法：speakers/others 传带编号与人称的串，如 "(S2) the female clerk" / "(S1) the girl"
    更强的一招：不说话的角色**直接不进这一镜**（写 "ONLY the girl is in this shot"）。
    """
    t = (f"SPEAKER LOCK — in this shot the ONLY person who speaks is {speakers}; that person's lips clearly move "
         "as the lines are spoken and the voice comes from that person's mouth. ")
    if others:
        t += (f"Nobody else speaks: {others} keeps their lips completely closed and still — they never open their "
              "mouth, never mouth any word and are never the source of any voice. ")
    return t


# ── 使用者/产品演示铁律（宝哥 2026-09-26 令）──
RIDER_RULE = (
    "RIDER RULE: the rider is an ordinary healthy person — able-bodied, able to stand and walk normally, nothing "
    "wrong with their legs. NEVER write a disability, paralysis or 'cannot walk / no support under the feet' into "
    "the character: the model reacts by deleting their legs from the picture. They ride the product themselves — "
    "one hand rests on its control whenever it moves — and NOBODY EVER PUSHES IT: no hand ever grips the backrest "
    "or the push handles, nobody walks behind pushing it, nobody rolls it along beside them. Whenever they are "
    "seated, BOTH LEGS AND BOTH FEET ALWAYS STAY FULLY VISIBLE in frame with the feet resting flat on the "
    "footplates — never cropped, never hidden, never missing, never dangling out of the picture.\n"
    "SINGLE UNIT: exactly one product appears and it is the same one in every shot; it matches the reference "
    "images exactly and never deforms, morphs or turns into a different kind of vehicle."
)

# ── 产品收尾镜（剪辑手法，非提示词）──
WIDE_TAIL_NOTE = (
    "H3 无法在说词时持住宽景（只肯在宽景待 1-2 秒就推回特写），且宽景常落在说完话的静音段被明快档裁掉。"
    "要「品牌句 + 产品全貌」时，用 tools/append_wide_tail.py 把生片里的宽景剪出来做成结尾收尾镜。"
)
