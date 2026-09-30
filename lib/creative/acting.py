"""ACTING 表演层（Phase 7 必做任务 4）。

问题：`lib/hellgrind.acting_block()` 只会把整篇表演主档案**原文**拼进去，
一旦逐镜调用，同一段 200 词档案会在 4 个镜头里重复 4 遍 —— 既是浪费，
也会让模型把"同一个表情"复制到每一镜。

做法：把主档案切成 7 个固定块（块序来自 ACTING 原文），逐镜挑**不同**的块，
每镜再配一条与叙事节拍对应的行为策略（tactic）。同一 spec 内绝不重复同一块。

公理不变：表演是压力下的行为，不是情绪展示。
"""
from __future__ import annotations

import re

from ..hellgrind import load_master

# ── 表演主档案的 7 个固定块（与 master_profile_template 的块序一致）──
_BLOCKS: tuple[tuple[str, re.Pattern], ...] = (
    ("engine", re.compile(r"\b(?:He|She|They)\s+runs on one engine:", re.I)),
    ("voice", re.compile(r"Vocal profile:", re.I)),
    ("tics", re.compile(r"Key physical habits and tics:", re.I)),
    ("eyes", re.compile(r"Eye life:", re.I)),
    ("walk", re.compile(r"Walking style:", re.I)),
    ("crack", re.compile(r"However, when", re.I)),
    ("soften", re.compile(r"The only thing (?:their|his|her) face truly softens for is", re.I)),
)

# 逐镜取块的顺序：先"看得见的小动作"，再态度，最后是面具裂纹。
CLAUSE_ORDER: tuple[str, ...] = ("tics", "walk", "crack", "eyes", "engine", "soften", "voice")

# 没有主档案的槽位用"身份感小动作"兜底（不是随便编情绪）
SLOT_TICS: dict[str, str] = {
    "@elder_male": "keeps one hand braced on whatever is nearest once he has decided something",
    "@elder_female": "plants both feet and folds her arms when she is being talked over",
    "@mid_male": "checks the other person's face for a reaction before finishing the line",
    "@mid_female": "straightens her cuff and lifts her chin when contradicted",
    "@young_male": "shifts his weight foot to foot while waiting to be believed",
    "@young_female": "tucks her hair back and holds the look a beat longer than expected",
    "@teen_boy": "bounces on the balls of his feet and glances at the door",
    "@child": "swings their legs and stares openly at whatever is new",
    "@courier": "taps the delivery box twice before speaking",
    "@neighbor_any": "leans in, hands on hips, watching for the punchline",
    "@western_elder": "keeps one hand braced on whatever is nearest once he has decided something",
    "@western_adult": "checks the other person's face for a reaction before finishing the line",
    "@western_young": "shifts his weight foot to foot while waiting to be believed",
}

# 叙事节拍 → 可见的行为策略（每镜一句，不描述情绪，只描述行为）
BEAT_TACTICS: dict[str, str] = {
    "钩子": "opens by putting a hand or the object between the other person and the camera to claim attention",
    "冲突/悬念": "presses the point and holds eye contact a beat too long, refusing to look away first",
    "演示/转折": "switches from talking to doing — the body commits before the words finish",
    "收口卖点": "settles, squares up and delivers the last line flat and certain",
    "回味": "lets the shoulders drop and watches the other person react instead of speaking",
}
_DEFAULT_TACTIC = "keeps the beat physical — a small gesture, a glance, a change of posture"

# 槽位 → 表演主档案（有真档案就用真档案；没有就退回 SLOT_TICS）
PROFILE_ALIAS: dict[str, str] = {
    "@elder_male": "elder",
    "@neighbor_any": "elder",
    "@western_elder": "elder",
    "@elder_female": "scene_G5_elder",
    "@mid_male": "son",
    "@mid_female": "scene_G5_son",
    "@young_male": "dark_knight",
    "@young_female": "dark_knight",
    "@teen_boy": "son",
    "@child": "son",
    "@courier": "son",
    "@western_adult": "blue_hero",
    "@western_young": "blue_hero",
}

_BLOCK_CUT = re.compile(r"Voice\s*\(verbatim", re.I)


def profile_for(ref: str) -> str:
    """角色引用（@槽位 或档案 id）→ 表演主档案 id（没有返回空串）。"""
    key = str(ref or "").strip()
    if not key:
        return ""
    cand = PROFILE_ALIAS.get(key, key)
    return cand if load_master(cand) else ""


def role_label(ref: str) -> str:
    """提示词里点名用的大写代号（WANG / (S1) …）。"""
    pid = profile_for(ref)
    if pid:
        text = load_master(pid)
        m = re.search(r"character acting as\s+([A-Z][A-Z'\- ]{1,20})", text, re.I)
        if m:
            return m.group(1).strip().rstrip(".").upper()
        return pid.upper()
    return "THE SPEAKER"


def blocks(role_id: str) -> dict[str, str]:
    """把主档案切成 {块名: 文本}（切不出来就返回空 dict）。"""
    text = load_master(role_id)
    if not text:
        return {}
    cut = _BLOCK_CUT.search(text)
    if cut:
        text = text[:cut.start()]
    marks: list[tuple[str, int, int]] = []
    for name, pattern in _BLOCKS:
        m = pattern.search(text)
        if m:
            marks.append((name, m.start(), m.end()))
    marks.sort(key=lambda m: m[1])
    out: dict[str, str] = {}
    for i, (name, _, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out[name] = " ".join(text[end:stop].split()).strip(" .")
    return {k: v for k, v in out.items() if v}


def clauses(role_id: str) -> list[str]:
    """按 CLAUSE_ORDER 输出该角色的行为子句（供逐镜轮换）。"""
    blk = blocks(role_id)
    return [f"{name}: {blk[name]}" for name in CLAUSE_ORDER if blk.get(name)]


def beat_line(ref: str, beat: str, *, used: set[str] | None = None) -> str:
    """一镜一条表演指令：行为策略 + 未被用过的角色子句。同 spec 内不重复。"""
    used = used if used is not None else set()
    pid = profile_for(ref)
    label = role_label(ref)
    tactic = BEAT_TACTICS.get(str(beat or "").strip(), _DEFAULT_TACTIC)
    pool: list[str] = []
    if pid:
        blk = blocks(pid)
        pool = [blk[name] for name in CLAUSE_ORDER if blk.get(name)]
    if not pool:
        tics = SLOT_TICS.get(str(ref or "").strip())
        pool = [tics] if tics else []
    clause = ""
    for cand in pool:
        if cand not in used:
            clause = cand
            break
    if clause:
        # 记账用**原文**：早先这里先把首字母大写再入 set，检查却拿原文比对，
        # 于是"已用过"永远命中不了，同一角色跨镜又会拿到同一句（Phase 7 实测）。
        used.add(clause)
        clause = clause[0].upper() + clause[1:]
    head = f"{label}: {tactic}"
    return f"{head}. {clause}." if clause else f"{head}."
