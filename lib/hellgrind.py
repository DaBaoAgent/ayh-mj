"""Higgsfield《Hell Grind》三件套接入层（2026-09-26 宝哥令接入 ayh-mj）

来源：Higgsfield 官方开源生产技能（95 分钟 AI 长片《Hell Grind》的提示词系统）
  · LIRA      — 图像提示词优化（人物定妆照 / 场景板 / 道具表）  → 本仓「定妆照」环节
  · CINEDANCE — 视频提示词导演（V4，Seedance 2.0 / H3）         → 本仓「one-take 提示词」环节
  · ACTING    — 表演系统（角色行为层，压力下的行为≠情绪展示）  → 本仓新增的「表演层」

本地完整原文：D:\\@kaifa\\higgsfield-hell-grind-skills\\
Hermes 技能：media/lira-image-prompts · media/cinedance-seedance · media/acting-performance

⚠️ 冲突处理铁律：本模块只提供三件套的**通用规则骨架**。
ayh-mj 的实测坑位（H3 能力边界 / SPEAKER LOCK / 产品三图铁律 / prompt 10000 字符上限）
**优先于**三件套的通用规则；两者叠加时以 ayh-mj 为准。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTING_DIR = ROOT / "assets" / "cast" / "acting"


# ══════════════════════════════════════════════════════════════════
# LIRA — 图像提示词（定妆照 / 场景板）
# ══════════════════════════════════════════════════════════════════
# 核心方法（原文 § DIAGNOSE）：先把"这张图会怎么失败"诊断出来，再针对性下锁。
# 典型失败模式 → 锁：
#   塑料皮肤/过度磨皮 → 「真实感三连」锁（可见毛孔、细纹、无美颜）
#   脸崩/换脸          → Soul ID / 参考图锁（ayh-mj 侧 = 已有定妆图做 --ref）
#   族裔漂移           → 显式写族裔 + 禁止默认值
#   构图跑偏           → 显式景别 + 占画面比例
#   文字乱码           → 禁止画面文字（产品品牌字除外）

# Lira 的真实感锁（ayh-mj 已有 REALISM 段，此处为图像版）
LIRA_REALISM = (
    "photorealistic documentary photography, candid unretouched photo, "
    "no beauty filter, no makeup, no retouching, ultra-realistic skin texture with visible pores and "
    "natural imperfections, natural daylight with soft shadows"
)

# 图像模型的"手术式编辑"顺序（Lira：任何已有图的后处理先走编辑模型，不要整图重跑）
LIRA_EDIT_ORDER = (
    "post-processing an existing image: edit in place first (mask-composited point edit); "
    "never run an image through a generative model a second time in full"
)


def cast_prompt(desc: str, *, shot: str = "full", size_hint: str = "", ethnicity: str = "Chinese",
                scene: str = "", purpose: str = "", quiet: bool = False, extra: str = "") -> str:
    """LIRA 口径的人物定妆照提示词。

    desc      角色外形描述（年龄/发型/脸/服装——具体，不要形容词堆砌）
    shot      full=全身（默认，供 H3 参考图） / portrait=半身 / closeup=特写
    purpose   用途诊断（写清"这张图要解决下游什么问题"，Lira 的第一步）
    quiet     闭嘴版（非说话人参考图——H3 会把参考图表情带到人物脸上，ayh-mj 实测坑）
    """
    shot_clause = {
        "full": "Full body shot — the entire body from head to toe is inside the frame, both shoes and the "
                "ground beneath them clearly visible, nothing cropped or cut off at the bottom edge, "
                "standing naturally, vertical composition",
        "portrait": "Medium close-up portrait, waist-up, looking at the camera, vertical composition",
        "closeup": "Tight head-and-shoulders portrait, looking at the camera, vertical composition",
    }.get(shot, shot)

    # 族裔锁（ayh-mj 实测：不写会被模型默认成亚洲脸）；desc 已写则不再重复
    eth = f"{ethnicity} " if ethnicity and ethnicity.lower() not in desc.lower() else ""
    # 闭嘴锁（quiet 版）
    mouth = ("Lips fully closed, mouth completely at rest, calm neutral expression with no mouth opening. "
             if quiet else "")
    diag = f"[PURPOSE] {purpose}. " if purpose else ""
    sc = f"[SETTING] {scene}. " if scene else ""
    sz = f"{size_hint}. " if size_hint else ""

    return (
        f"{diag}{LIRA_REALISM}. "
        f"{eth}{desc}. "
        f"{shot_clause}. {sz}{mouth}{sc}"
        "No text, no watermark, no logo anywhere in the image. "
        "Not a fashion photo, not a studio photo — an ordinary everyday person captured candidly."
        + (f" {extra}" if extra else "")
    )


# ══════════════════════════════════════════════════════════════════
# CINEDANCE — 视频镜头语言（补 ayh-mj 缺的结构化镜头段）
# ══════════════════════════════════════════════════════════════════
# CINEDANCE 相对 ayh-mj 原有写法的**增量**（原文核心，ayh-mj 此前没有）：
#   ① 镜头 = 对角线视场角(度) + 机位距离 + 可见结果，不写毫米/光圈
#   ② 首帧占位（first-frame occupancy）——第一帧就必须定住空间关系
#   ③ 空间调度（blocking）——每个人在哪、离谁多远、朝哪
#   ④ 视线与身体朝向**分开写**（gaze ≠ body facing）
#   ⑤ 光作为锁——光源/方向/机位侧/曝光优先，一次锁死不逐镜改
#   ⑥ 物理锁——重力、接触、无悬空
#   ⑦ 默认一镜到底；切镜必须有理由；转场必须命名

CINEDANCE_CONSTANTS = (
    "CINEDANCE FILM LANGUAGE: optics are written as a diagonal field of view in degrees with the camera "
    "distance and the visible outcome — never millimetres or f-stops. Each shot's first frame already fixes "
    "who is where, how far apart and facing which way. One lighting lock holds for the whole video. Physics "
    "hold: wheels stay on the ground, nothing floats."
)


def shot_block(idx: int, times: str, desc: str, *, fov_deg: str = "", camera: str = "",
               occupancy: str = "", light: str = "") -> str:
    """CINEDANCE 口径的单镜段落。

    idx        镜号（1 起）
    times      时间轴，如 "0 to 4 seconds"
    desc       动作/台词/表演描述（主体）
    fov_deg    对角线视场角，如 "42 degrees"（不写毫米）
    camera     机位与运动，如 "camera 2.5 metres away at chest height, slow push-in"
    occupancy  首帧占位，如 "both people fill the middle band, product low-centre"
    light      光锁（只在首镜写一次即可）
    """
    parts = [f"[Shot {idx}, {times}]"]
    if fov_deg or camera:
        parts.append(" ".join(x for x in [f"Camera: diagonal field of view {fov_deg}," if fov_deg else "",
                                          camera] if x).strip().rstrip(",") + ".")
    if occupancy:
        parts.append(f"First frame: {occupancy}.")
    if light:
        parts.append(f"Light: {light}.")
    parts.append(desc)
    return " ".join(parts)


# ══════════════════════════════════════════════════════════════════
# ACTING — 表演层（ayh-mj 此前完全缺失的一层）
# ══════════════════════════════════════════════════════════════════
# 公理：表演是**压力下的行为**，不是情绪展示。
# 落地物：① 每角色一份 150-220 词表演主档案（写一次，逐场改写而非粘贴）
#         ② 眼神必须给任务（死鱼眼是 AI 表演第一号破绽）
#         ③ 节拍变化必须可见（停顿/姿态/语速/视线）
#         ④ 音色锁定（ayh-mj 侧 = assets/cast/voice/<id>.mp3，即 ref_audio）

def master_path(role_id: str) -> Path:
    return ACTING_DIR / f"{role_id}.md"


def load_master(role_id: str) -> str:
    """读取角色的表演主档案（不存在返回空串）。"""
    p = master_path(role_id)
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8")
    # 去掉 markdown 注释/标题，只留正文段落
    txt = re.sub(r"^#.*$", "", txt, flags=re.M)
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    return " ".join(txt.split())


# 眼神生命（每镜必写——H3 默认给的就是死鱼眼）
EYE_RULE = (
    "EYE LIFE — the eyes stay alive and purposeful throughout: quick natural micro-saccades, natural blink "
    "rate tied to the emotional state, wet live catchlights, and the eyes always given a task (checking the "
    "other person's face for a reaction, registering what was just said, darting to the product and back). "
    "The gaze keeps moving and settling — it never freezes into a glassy dead stare."
)


def acting_block(role_lines: list[str], *, eye: bool = True, beats: str = "") -> str:
    """拼装一镜的表演层。

    role_lines  逐角色一行的行为描述（形如 "As (S1) the girl: wants to ...; her tactic is ..."）
    beats       节拍变化描述（2-4 个可见变化；留空则不写）
    """
    if not role_lines:
        return ""
    t = "CHARACTER ACTING — performance is behaviour under pressure, never a display of emotion. " + " ".join(role_lines)
    if beats:
        t += f" Beat changes: {beats}."
    if eye:
        t += " " + EYE_RULE
    return t


def master_profile_template(role_id: str, *, age: str, build: str, engine: str, voice: str,
                            tics: str, walk: str, crack: str, soften: str = "") -> str:
    """按 ACTING 原文固定块序生成表演主档案骨架（写入 assets/cast/acting/<role_id>.md）。

    块序固定（不可调换）：身份体态 → 心理引擎 → 声线 → 习惯小动作 → 步态 → 「However, when X」面具裂纹 → 软化目标
    """
    body = (
        f"Character acting as {role_id.upper()}. {age}, {build}. {engine} "
        f"Vocal profile: {voice} "
        f"Key physical habits and tics: {tics} "
        f"Walking style: {walk} "
        f"However, when {crack}"
        + (f" The only thing their face truly softens for is {soften}." if soften else "")
    )
    return f"# {role_id} — 表演主档案（ACTING 系统）\n\n<!-- 150-220 词，一段话，块序固定；逐镜改写而非粘贴 -->\n\n{body}\n"


def ensure_dirs() -> None:
    ACTING_DIR.mkdir(parents=True, exist_ok=True)


# ── 供 prep 脚本一行接入：把三件套的常量塞进 H3 spec 的 extra_tail ──
def tail_constants(*, cinedance: bool = True, acting_of: list[str] | None = None) -> str:
    """返回可直接拼进 `extra_tail` 的三件套常量串（自动去重、控制长度）。"""
    out = []
    if cinedance:
        out.append(CINEDANCE_CONSTANTS)
    for rid in (acting_of or []):
        m = load_master(rid)
        if m:
            out.append(f"ACTING — {rid}: {m}")
    if acting_of:
        out.append(EYE_RULE)
    return " ".join(out)


if __name__ == "__main__":
    ensure_dirs()
    print(f"ACTING_DIR = {ACTING_DIR}")
    print(f"已有表演主档案: {[p.stem for p in ACTING_DIR.glob('*.md')] if ACTING_DIR.exists() else []}")
    print(f"\nCINEDANCE_CONSTANTS = {len(CINEDANCE_CONSTANTS)} 字符")
    print(f"EYE_RULE           = {len(EYE_RULE)} 字符")
