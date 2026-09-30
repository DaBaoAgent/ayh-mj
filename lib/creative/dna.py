"""CreativeDNA（Phase 5）—— 一条视频的创意基因：结构化、可校验、可追溯。

CreativeDNA 是"选题 / 创意"层的唯一数据结构：
  · Planner 先批量生成 10–20 个**廉价结构化**候选（不写散文、不写 H3 大 prompt）；
  · CreativeDirector 按 10 个维度打分 → 取 top3 → 定稿；
  · 定稿 DNA 连同评分落 artifact，出片后仍能回溯"为什么这么拍"。

20 个字段来自迭代计划 §Phase 5「CreativeDNA 建议字段」，一个不多一个不少。
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass, field

# ── 受控词表（候选必须落在词表内，避免"看起来合理就通过"）──────────────
AUDIENCES = (
    "子女代购决策者", "银发自用人群", "家庭照护者", "社区邻里围观者", "图文比价人群",
)
GOALS = (
    "让人记住一个卖点", "促成咨询留言", "建立安全信任", "场景代入种草", "制造讨论转发",
)
HOOK_TYPES = (
    "悬念设问", "冲突质问", "反差打脸", "夸张数字", "痛点共鸣", "视觉奇观", "身份代入", "神秘物件",
)
NARRATIVE_ARCS = (
    "先抑后扬", "打脸反转", "悬念揭晓", "重复强化", "对比实验", "日常纪实", "误会解除", "情感递进",
)
SHOT_PATTERNS = (
    "四镜双人对撞", "五镜生活流", "手持街访", "悬念三段式", "三镜魔性循环",
    "实验对比双线", "POV主观视角", "无对白肢体三段", "五镜情感递进", "评论区回应式",
)
PRODUCT_ROLES = ("解题工具", "对比主角", "配角道具", "惊喜礼物", "实验对象")
CONFLICT_TYPES = (
    "质疑能力", "价格攀比", "家人反对", "陌生人误解", "身体不便", "旧物对照", "时间紧迫", "无冲突氛围向",
)
VISUAL_MOTIFS = (
    "折叠收放", "遥控轨迹", "坡道爬升", "后备箱装车", "单手提起", "轮圈细节", "雨夜灯光", "老照片对比",
)
CAMERA_LANGUAGES = (
    "固定机位中景", "手持跟拍", "近景特写", "俯拍全景", "低角度仰拍", "第一人称POV", "侧移横移",
)
DIALOGUE_MODES = ("双人对白", "单人口播", "街访问答", "无对白", "画外音旁白", "字幕驱动")
AUDIO_MODES = ("现场同期声", "BGM+音效", "旁白+BGM", "纯音效", "人声+字幕")

# 20 个必填字段（顺序即落库 / 展示顺序）
REQUIRED_FIELDS: tuple[str, ...] = (
    "audience", "goal", "hotspot", "genre", "angle", "sales_point", "hook_type",
    "narrative_arc", "shot_pattern", "cast_pattern", "product_role", "conflict_type",
    "visual_motif", "camera_language", "dialogue_mode", "audio_mode", "payoff",
    "ending", "CTA", "risk_flags",
)

# 受控词表字段 → 允许取值（genre / angle / sales_point 是池 id，另行校验）
VOCAB: dict[str, tuple[str, ...]] = {
    "audience": AUDIENCES, "goal": GOALS, "hook_type": HOOK_TYPES,
    "narrative_arc": NARRATIVE_ARCS, "shot_pattern": SHOT_PATTERNS,
    "product_role": PRODUCT_ROLES, "conflict_type": CONFLICT_TYPES,
    "visual_motif": VISUAL_MOTIFS, "camera_language": CAMERA_LANGUAGES,
    "dialogue_mode": DIALOGUE_MODES, "audio_mode": AUDIO_MODES,
}

# 数值/认证类卖点在 Phase 6 Claims Registry 落地前一律打标，禁止当"事实"直接念
CLAIM_RISK_FLAG = "数值承诺待核验"
MIN_TEXT = 4          # payoff / ending / CTA 至少写清楚，不能是占位空串


@dataclass
class CreativeDNA:
    """一条视频的创意基因（20 字段）。空串允许出现在"构建中"，但 validate 会报出来。"""

    audience: str = ""
    goal: str = ""
    hotspot: str = ""
    genre: str = ""
    angle: str = ""
    sales_point: str = ""
    hook_type: str = ""
    narrative_arc: str = ""
    shot_pattern: str = ""
    cast_pattern: str = ""
    product_role: str = ""
    conflict_type: str = ""
    visual_motif: str = ""
    camera_language: str = ""
    dialogue_mode: str = ""
    audio_mode: str = ""
    payoff: str = ""
    ending: str = ""
    CTA: str = ""
    risk_flags: list[str] = field(default_factory=list)

    # ── 序列化 ─────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CreativeDNA:
        known = set(REQUIRED_FIELDS)
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        flags = kwargs.get("risk_flags")
        kwargs["risk_flags"] = list(flags) if isinstance(flags, list) else []
        return cls(**kwargs)

    # ── 校验 ───────────────────────────────────────────────────
    def validate(self) -> list[str]:
        """返回问题清单（空 = 合格）。词表外的取值一律算问题，不许"看着合理就放过"。"""
        problems: list[str] = []
        for name in REQUIRED_FIELDS:
            value = getattr(self, name)
            if name == "risk_flags":
                if not isinstance(value, list):
                    problems.append("risk_flags 必须是列表")
                continue
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{name} 为空")
        for name, allowed in VOCAB.items():
            value = getattr(self, name)
            if value and value not in allowed:
                problems.append(f"{name}={value!r} 不在词表内")
        for name in ("payoff", "ending", "CTA"):
            value = getattr(self, name)
            if isinstance(value, str) and 0 < len(value.strip()) < MIN_TEXT:
                problems.append(f"{name} 太短（<{MIN_TEXT} 字），等于没写")
        if self.cast_pattern and not self.cast_pattern.startswith("@"):
            problems.append("cast_pattern 必须是 @槽位 组合（如 @elder_male+@mid_male）")
        # 三个"池 id"字段必须在真实池子里（防手写错 id 混进生产）
        with suppress(ImportError, KeyError):
            from ..angles import ANGLES
            from ..genres import GENRES
            from ..products import SALES_POINTS
            if self.genre and self.genre not in {g["id"] for g in GENRES}:
                problems.append(f"genre={self.genre!r} 不在片型池内")
            if self.angle and self.angle not in {a["id"] for a in ANGLES}:
                problems.append(f"angle={self.angle!r} 不在叙事思路池内")
            if self.sales_point and self.sales_point not in {p["id"] for p in SALES_POINTS}:
                problems.append(f"sales_point={self.sales_point!r} 不在卖点池内")
        return problems

    # ── 指纹（供同日去重 / 幂等）───────────────────────────────
    def signature(self) -> tuple[str, str, str]:
        """故事骨架指纹：片型 + 钩子类型 + 镜头结构（验收要求的三维差异）。"""
        return (self.genre, self.hook_type, self.shot_pattern)

    def cast_signature(self) -> str:
        return self.cast_pattern.strip()

    def as_row(self) -> dict:
        """便于打印 / 落库的扁平行（含骨架指纹）。"""
        row = self.to_dict()
        row["signature"] = list(self.signature())
        return row
