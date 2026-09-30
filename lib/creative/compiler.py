"""PromptCompiler（Phase 7 必做任务 2/3/4/5/6/13）—— StorySpec → provider prompt 的唯一实现。

为什么要有它：此前 H3 大 prompt 是在 prep 脚本里手工拼的（`tools/prep_*.py` 各贴一遍
SPEAKER LOCK / GAZE / RIDER / 产品保真），改一处要改 N 处。现在只有一个入口：

    spec（结构 + 台词 + CreativeDNA） ──PromptCompiler──▶ prompt + 元数据

职责边界
  · 只做**编译**：不选题、不写台词、不选工作流、不花钱；
  · CINEDANCE 按片型动态启用（任务 3）——剧情/短剧/魔性/脑洞/反差/对比片要电影语言总纲，
    生活流/街访/情感/悬念/回应型不要（真实感优先，套上反而变"广告感"）；
  · ACTING 逐镜给不同行为节拍（任务 4），绝不把主档案原文重复塞每镜；
  · SPEAKER LOCK / GAZE / RIDER / 产品保真按场景注入（任务 5），prep 脚本不再粘贴；
  · Prompt Budgeter（任务 6）：提交前算长度、去重重复长句、必要时压缩；压不下来就
    **在付费之前**抛 PromptBudgetExceeded；
  · 编译器版本 / spec 版本 / 事实层 digest 全部写进 artifact（任务 13）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..hellgrind import EYE_RULE, shot_block
from ..products import ROOT as _ROOT
from . import acting as acting_mod
from . import prescreen as prescreen_mod

COMPILER_VERSION = "prompt-compiler/1.0"
PROMPT_MAX = 10000
PROMPT_SAFE = 9800

# 片型 → 是否启用 CINEDANCE 电影语言总纲
CINEDANCE_GENRES: frozenset[str] = frozenset({"G1", "G2", "G3", "G4", "G8", "G10"})
# 面对面说话（要 GAZE 规则）
GAZE_DIALOGUE_MODES: frozenset[str] = frozenset({"双人对白", "街访问答"})
# 台词呈现方式（与官方 <d> 语法 / docs/rules-dialogue.md 对齐）
DIALOGUE_LANG = "Chinese"          # 台词保留中文原文（R15）
VOICEOVER_MODES: frozenset[str] = frozenset({"画外音旁白"})
CAPTION_MODES: frozenset[str] = frozenset({"字幕驱动"})
# 必须有成句台词的模式（字幕驱动靠画面文字，不算口播）
SPEECH_MODES: frozenset[str] = frozenset({"双人对白", "单人口播", "街访问答", "画外音旁白"})


def needs_dialogue(dialogue_mode: str) -> bool:
    """这个台词模式是不是"必须有词"？—— preflight 靠它决定要不要拦。"""
    return str(dialogue_mode or "") in SPEECH_MODES
# 静态门禁的包装头（check_dialogue.mjs 靠 duration="N" 算语速预算）
GATE_WRAPPER = '<h3:video duration="{duration}" resolution="{resolution}">\n<text:Value>\n'
GATE_WRAPPER_END = "\n</text:Value>"
# 值得用 0.5s 冲击开场的钩子
COLD_OPEN_HOOKS: frozenset[str] = frozenset({
    "悬念设问", "冲突质问", "反差打脸", "夸张数字", "视觉奇观", "神秘物件",
})
# 产品是"被用起来"的角色 → 需要 RIDER 铁律（腿/脚可见、不许人推）
RIDER_PRODUCT_ROLES: frozenset[str] = frozenset({"解题工具", "对比主角", "实验对象"})

# 镜头语言 → (对角线视场角, 机位, 首帧占位)
CAMERA_MAP: dict[str, tuple[str, str, str]] = {
    "固定机位中景": ("42 degrees", "camera 2.5 metres away at chest height, locked off",
                 "both subjects fill the middle band of the frame, product low-centre"),
    "手持跟拍": ("48 degrees", "handheld camera at chest height, gentle sway, following the subject",
              "the subject fills the left two-thirds, product moving with them"),
    "近景特写": ("30 degrees", "camera 1.1 metres away at eye height, slow push-in",
              "one face and one detail fill the frame"),
    "俯拍全景": ("60 degrees", "camera 3.2 metres away, slightly above head height, static",
              "the whole room and both people sit inside the frame, product on the floor line"),
    "低角度仰拍": ("55 degrees", "camera 60 centimetres off the ground, tilted up",
               "the product towers in the lower third, the person above it"),
    "第一人称POV": ("70 degrees", "camera at the subject's own eye height, no cut to a third person",
                "the subject's own hands and the product fill the frame"),
    "侧移横移": ("45 degrees", "camera tracks sideways at chest height, no push-in",
             "the pair spread across the frame, product between them"),
}
_DEFAULT_CAMERA = ("45 degrees", "camera at chest height, gentle movement", "subject centred")

# 音轨模式 → overall_soundscape 一句话
SOUNDSCAPES: dict[str, str] = {
    "现场同期声": "live location sound only — footsteps, wheels on the ground, fabric, breath; no music",
    "BGM+音效": "light upbeat music bed with clean diegetic hits on the cuts",
    "旁白+BGM": "warm music bed under a single close-mic voice-over, room tone underneath",
    "纯音效": "no spoken lines at all — only diegetic effects: clicks, folds, wheels, cloth",
    "人声+字幕": "clean dialogue with light room tone, no music",
}

_LONG_SENTENCE = 50          # 归一化后长度 ≥ 此值的重复长句才会被去重


class PromptBudgetExceeded(Exception):
    """prompt 超限且压缩无效 —— 必须在付费提交之前抛出（任务 6）。"""

    error_code = "PROMPT_TOO_LONG"

    def __init__(self, chars: int, limit: int, dropped: int = 0) -> None:
        self.chars, self.limit, self.dropped = int(chars), int(limit), int(dropped)
        super().__init__(f"prompt {chars} 字符 > 上限 {limit}（去重 {dropped} 句后仍超限）"
                         "—— 未提交、0 花费")


@dataclass
class PromptBudget:
    chars: int = 0
    limit: int = PROMPT_MAX
    safe: int = PROMPT_SAFE
    dropped_sentences: int = 0
    compressed: bool = False
    chars_after: int | None = None

    def to_dict(self) -> dict:
        return {"chars": self.chars, "limit": self.limit, "safe": self.safe,
                "dropped_sentences": self.dropped_sentences,
                "compressed": self.compressed, "chars_after": self.chars_after}


@dataclass
class CompiledPrompt:
    """编译结果（prompt + 可追溯元数据）。"""

    uid: str
    prompt: str
    provider: str = "autodl"
    compiler_version: str = COMPILER_VERSION
    spec_version: str = ""
    layers: list[str] = field(default_factory=list)
    cinedance: bool = False
    shot_count: int = 0
    line_count: int = 0
    acting_lines: list[str] = field(default_factory=list)
    facts_digest: str = ""
    budget: PromptBudget = field(default_factory=PromptBudget)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"compiler_version": self.compiler_version, "provider": self.provider,
                "spec_version": self.spec_version, "layers": list(self.layers),
                "cinedance": self.cinedance, "shot_count": self.shot_count,
                "line_count": self.line_count, "acting_lines": list(self.acting_lines),
                "facts_digest": self.facts_digest,
                "budget": self.budget.to_dict(), "warnings": list(self.warnings),
                "chars": len(self.prompt)}


# ── 归一化：StorySpec 对象或 spec dict 都能编译 ──────────────────────
def _view(spec) -> dict:
    if isinstance(spec, dict):
        creative = spec.get("creative") or {}
        story = spec.get("story_spec") or {}
        dna = dict(creative.get("dna") or spec.get("dna") or {})
        return {
            "uid": str(spec.get("job_uid") or spec.get("uid") or ""),
            "title": str(spec.get("title") or ""),
            "duration": int(spec.get("duration") or 15),
            # 片型可能在 creative.genre，也可能只在 dna.genre（Planner 落盘只写后者）；
            # 两条路径必须编出同一份 prompt，否则 CINEDANCE 开关会随"对象/字典"而变。
            "genre": str(creative.get("genre") or spec.get("genre") or dna.get("genre") or ""),
            "structure": str(creative.get("structure") or spec.get("structure_id") or ""),
            "dna": dna,
            "shots": list(story.get("shots") or spec.get("shots") or []),
            "lines": list(spec.get("lines") or story.get("lines") or []),
            "claim_ids": list(spec.get("claim_ids") or creative.get("claim_ids") or []),
            "spec_version": str(spec.get("spec_version") or ""),
        }
    dna = getattr(spec, "dna", None)
    return {
        "uid": str(getattr(spec, "uid", "") or ""),
        "title": str(getattr(spec, "title", "") or ""),
        "duration": int(getattr(spec, "duration", 15) or 15),
        "genre": str(getattr(dna, "genre", "") or "") if dna else "",
        "structure": str(getattr(spec, "structure_id", "") or ""),
        "dna": dna.to_dict() if dna is not None else {},
        "shots": [dict(s) for s in (getattr(spec, "shots", None) or [])],
        "lines": [dict(x) for x in (getattr(spec, "lines", None) or [])],
        "claim_ids": list(getattr(spec, "claim_ids", None) or []),
        "spec_version": str(getattr(spec, "spec_version", "") or ""),
    }


def time_plan(duration: int, n_shots: int) -> list[tuple[int, int]]:
    """把时长按整数秒均分（15s/4 镜 → 4,4,4,3），不出现 3.8s 这种时间轴。"""
    n = max(1, int(n_shots))
    duration = max(n, int(duration))
    base, extra = divmod(duration, n)
    out: list[tuple[int, int]] = []
    cursor = 0
    for i in range(n):
        span = base + (1 if i < extra else 0)
        out.append((cursor, cursor + span))
        cursor += span
    return out


def _speaker_slots(dna: dict) -> list[str]:
    pattern = str(dna.get("cast_pattern") or "")
    return [s for s in pattern.split("+") if s.strip()]


def lines_from_file(uid: str, n_shots: int, dialogue_mode: str,
                    slots: list[str]) -> list[dict]:
    """回退：读仓库既有约定 docs/onetake_lines_<uid>.txt，按镜数**均摊**句数。

    句数不再固定 8 —— 稿子写几句就是几句，镜数是 spec 说了算（Phase 7 任务 1）。
    Planner 也调这个函数，保证"落进 spec 的台词"与"编译器回退读到的台词"永远一致。
    """
    path = _ROOT / "docs" / f"onetake_lines_{uid}.txt"
    if not path.is_file():
        return []
    raw = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not raw:
        return []
    two = dialogue_mode == "双人对白" and len(slots) >= 2
    out: list[dict] = []
    for i, text in enumerate(raw):
        shot = min(n_shots, 1 + int(i * n_shots / len(raw)))
        speaker = (slots[0] if (two and i % 2 == 0) else slots[1 % len(slots)]) if slots else "S1"
        out.append({"shot": shot, "speaker": speaker, "text": text})
    return out


def _normalise_lines(view: dict) -> list[dict]:
    slots = _speaker_slots(view["dna"])
    rows = view["lines"]
    if not rows:
        rows = lines_from_file(view["uid"], max(1, len(view["shots"])),
                               str(view["dna"].get("dialogue_mode") or ""), slots)
    out: list[dict] = []
    for row in rows:
        if isinstance(row, str):
            out.append({"shot": 1, "speaker": slots[0] if slots else "S1", "text": row})
            continue
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or row.get("line") or "").strip()
        if not text:
            continue
        out.append({"shot": int(row.get("shot") or 1),
                    "speaker": str(row.get("speaker") or (slots[0] if slots else "S1")),
                    "text": text})
    return out


def _spoken_label(speaker: str, index: int) -> str:
    pid = acting_mod.profile_for(speaker)
    label = acting_mod.role_label(speaker)
    if pid or label != "THE SPEAKER":
        return f"({_S[index]}) {label}"
    return f"({_S[index]}) {speaker}"


_S: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5")


def spoken_line(speaker: str, text: str, *, slot_index: int, mode: str = "") -> str:
    """一句台词的**唯一**渲染口径（官方 <d> 语法，见 docs/rules-dialogue.md R1/R7/R16）。

    · 双人对白/单人口播/街访问答 → `(S2) 儿子 says: <d>[Chinese] …</d>`
      —— 编号在 <d> 外、语言标签在 <d> 内，一个字都不改；
    · 画外音旁白 → 同一句里声明「画面人物嘴唇保持闭合」（R8 实测第一大错口型来源）；
    · 字幕驱动 → 画面内可见文字，**不进 <d>**（进了会被念出来），用英文双引号原样写（R16）。
    """
    who = _spoken_label(speaker, slot_index)
    body = str(text or "").strip()
    if mode in CAPTION_MODES:
        return f'{who} — on-screen Chinese caption reads "{body}" (visible text, never spoken).'
    if mode in VOICEOVER_MODES:
        # 措辞必须命中静态门禁 R8 的"嘴唇保持闭合"句式（lips remain completely closed），
        # 否则画外音片会因为"提到旁白却没声明口型"被判 ERROR。
        return (f"{who} says in an off-screen voiceover: <d>[{DIALOGUE_LANG}] {body}</d> "
                "while the person visible in frame says nothing — lips remain "
                "completely closed for the whole line.")
    return f"{who} says: <d>[{DIALOGUE_LANG}] {body}</d>"


def gate_text(prompt: str, *, duration: int, resolution: str = "768p竖") -> str:
    """静态门禁（tools/check_dialogue.mjs）吃的 payload —— 与产线同口径。"""
    return (GATE_WRAPPER.format(duration=int(duration), resolution=resolution)
            + str(prompt or "") + GATE_WRAPPER_END)


# ── 预算器（任务 6）────────────────────────────────────────────────
_WS = re.compile(r"\s+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def budget_prompt(layers: list[tuple[str, str]], *, limit: int = PROMPT_MAX,
                  safe: int = PROMPT_SAFE) -> tuple[str, PromptBudget]:
    """拼装 + 去重 + （必要时）压缩；仍然超限就抛 PromptBudgetExceeded。

    去重只针对**归一化后 ≥50 字符且完全一样**的长句（逐镜重复的 SPEAKER LOCK /
    约束尾巴就是这种），不会动台词和镜头描述。
    """
    chunks: list[str] = []
    seen: set[str] = set()
    dropped = 0
    for _, body in layers:
        keep: list[str] = []
        for sentence in _split_sentences(body):
            key = _WS.sub(" ", sentence).strip().lower()
            if len(key) >= _LONG_SENTENCE and key in seen:
                dropped += 1
                continue
            if key:
                seen.add(key)
            keep.append(sentence)
        if keep:
            chunks.append(" ".join(keep))
    text = "\n\n".join(chunks).strip()
    budget = PromptBudget(chars=len(text), limit=limit, safe=safe, dropped_sentences=dropped)
    if len(text) > safe:
        squeezed = _WS.sub(" ", text.replace("\n\n", " ")).strip()
        if len(squeezed) < len(text):
            text, budget.compressed = squeezed, True
    budget.chars_after = len(text)
    if len(text) > limit:
        raise PromptBudgetExceeded(len(text), limit, dropped)
    return text, budget


# ── 编译器 ────────────────────────────────────────────────────────
class PromptCompiler:
    """StorySpec → provider prompt（唯一实现，prep 脚本与编排器共用）。"""

    def __init__(self, *, provider: str = "autodl", limit: int = PROMPT_MAX,
                 safe: int = PROMPT_SAFE) -> None:
        self.provider = provider
        self.limit = int(limit)
        self.safe = int(safe)

    # 事实层（产品参数）——唯一来源是 Claims Registry
    @staticmethod
    def facts_block(channel: str = "script") -> tuple[str, str]:
        try:
            from .. import claims as claims_mod
            reg = claims_mod.load()
            return reg.facts_block(channel), reg.digest()[:16]
        except Exception as exc:      # 注册表坏掉不能让编译静默产出"没有参数"的片
            return "", f"unavailable:{type(exc).__name__}"

    def compile(self, spec) -> CompiledPrompt:  # noqa: A003
        from ..prompt_parts import COLD_OPEN, GAZE, HARD_TAIL, PACE, REALISM, RIDER_RULE, speaker_lock
        view = _view(spec)
        dna = view["dna"]
        slots = _speaker_slots(dna)
        lines = _normalise_lines(view)
        shots = view["shots"]
        if not shots:
            shots = [{"index": i + 1, "beat": ""} for i in range(max(3, len(lines) or 3))]
        n_shots = len(shots)
        plan = time_plan(view["duration"], n_shots)

        cinedance = str(view["genre"] or "") in CINEDANCE_GENRES
        dialogue_mode = str(dna.get("dialogue_mode") or "")
        layers: list[tuple[str, str]] = []
        warnings: list[str] = []

        # ① 头部 + 电影语言（按片型动态启用）
        head = "integrated_multimodal_description: Live-action fun commercial in vertical framing."
        if cinedance:
            from ..hellgrind import CINEDANCE_CONSTANTS
            head = f"{head} {CINEDANCE_CONSTANTS}"
        layers.append(("header", head))

        # ② 真实感（全局一次）+ 节奏（只对"有台词"的片成立）
        # 无台词块时套 PACE 会写出 "everyone speaks ..."，静态门禁 R1 会判成
        # "提到了说话却没有台词块" → 这类片只留 REALISM。
        spoken = bool(lines) and dialogue_mode not in CAPTION_MODES
        layers.append(("pace_realism", f"{PACE} {REALISM}" if spoken else REALISM))

        # ③ 视线规则：只有面对面说话才要（单人 vlog / 无对白不套）
        if dialogue_mode in GAZE_DIALOGUE_MODES and len(slots) >= 2:
            layers.append(("gaze", GAZE))

        # ④ CAST：每个槽位一行 + 全局说话人规则（不再逐镜重复长声明）
        if slots:
            cast_rows = []
            for i, slot in enumerate(slots):
                pid = acting_mod.profile_for(slot)
                who = acting_mod.role_label(slot) if pid else slot
                cast_rows.append(f"({_S[i]}) {who} ({slot})")
            rule = ("SPEAKER RULE — every line belongs to exactly the person credited with it; "
                    "nobody else ever mouths a word; the voice always comes from the credited "
                    "speaker's own mouth.")
            layers.append(("cast", "CAST — " + "; ".join(cast_rows) + ". " + rule))
            layers.append(("eye_rule", EYE_RULE))

        # ⑤ 开场冲击（按钩子类型）
        if str(dna.get("hook_type") or "") in COLD_OPEN_HOOKS:
            layers.append(("cold_open", COLD_OPEN))

        # ⑥ 产品事实 + 单元保真（产品模型只在 claims registry 里有参数）
        facts, digest = self.facts_block("script")
        product_bits = ["SINGLE UNIT — exactly one product appears and it is the same one in "
                        "every shot; it matches the reference images exactly and never deforms, "
                        "morphs or turns into a different kind of vehicle; its own brand lettering "
                        "stays exactly as it appears in the reference images."]
        if facts:
            product_bits.append("PRODUCT FACTS (the only numbers you may show or say): " + facts)
        layers.append(("product", " ".join(product_bits)))

        # ⑦ 逐镜：镜头语言 + 台词 + SPEAKER LOCK + ACTING + RIDER
        used_clauses: set[str] = set()
        acting_lines: list[str] = []
        rider_needed = str(dna.get("product_role") or "") in RIDER_PRODUCT_ROLES
        for idx, shot in enumerate(shots, 1):
            beat = str(shot.get("beat") or "")
            a, b = plan[idx - 1]
            fov, camera, occupancy = CAMERA_MAP.get(
                str(dna.get("camera_language") or ""), _DEFAULT_CAMERA)
            shot_rows = [r for r in lines if int(r["shot"]) == idx]
            speakers = [r["speaker"] for r in shot_rows]
            desc_parts = [f"Beat: {beat}." if beat else "",
                          f"Product role: {dna.get('product_role') or 'props'}."
                          if dna.get("product_role") else ""]
            if shot.get("visual_motif"):
                desc_parts.append(f"Visual motif: {shot['visual_motif']}.")
            for r in shot_rows:
                slot_index = slots.index(r["speaker"]) if r["speaker"] in slots else 0
                desc_parts.append(spoken_line(r["speaker"], r["text"],
                                              slot_index=slot_index,
                                              mode=dialogue_mode))
            if not shot_rows:
                # 不许出现 "dialogue/says/speaks" 这类词：门禁 R1 会判成"提到了说话却没台词块"
                desc_parts.append("No spoken words in this shot — pure action and physical "
                                  "comedy carry it, every mouth stays closed.")
            block = shot_block(idx, f"{a} to {b} seconds",
                               " ".join(p for p in desc_parts if p),
                               fov_deg=fov, camera=camera, occupancy=occupancy)
            extra: list[str] = []
            if shot_rows:
                uniq = list(dict.fromkeys(speakers))
                others = [s for s in slots if s not in uniq]
                # SPEAKER LOCK 是"谁张嘴说这句"的锁；画面字幕/无对白片没人张嘴，
                # 加进来只会让 R1 报 "speaks"。
                if spoken:
                    extra.append(speaker_lock(", ".join(uniq), ", ".join(others)))
                for sp in uniq:
                    line = acting_mod.beat_line(sp, beat, used=used_clauses)
                    acting_lines.append(line)
                    extra.append("CHARACTER ACTING — " + line)
            if rider_needed or beat in ("演示/转折", "收口卖点"):
                extra.append(RIDER_RULE)
            extra.append("Hard cut.")
            layers.append((f"shot{idx}", block + "\n" + "\n".join(extra)))

        # ⑧ 声音 + 硬约束
        sound = SOUNDSCAPES.get(str(dna.get("audio_mode") or ""), "")
        if sound:
            layers.append(("soundscape", f"overall_soundscape: {sound}"))
        layers.append(("music", "non_diegetic_music: N/A"))
        layers.append(("hard_tail", f"Hard constraints: {HARD_TAIL}"))

        prompt, budget = budget_prompt(layers, limit=self.limit, safe=self.safe)
        if budget.compressed:
            warnings.append("prompt 超过安全线，已压缩空白（未删镜头/未改台词）")
        if budget.dropped_sentences:
            warnings.append(f"去重了 {budget.dropped_sentences} 句逐镜重复的长约束")
        return CompiledPrompt(uid=view["uid"], prompt=prompt, provider=self.provider,
                              spec_version=view["spec_version"],
                              layers=[name for name, _ in layers], cinedance=cinedance,
                              shot_count=n_shots,
                              line_count=sum(1 for _ in lines), acting_lines=acting_lines,
                              facts_digest=digest, budget=budget, warnings=warnings)


def compile_spec(spec, **kwargs) -> CompiledPrompt:
    """一行入口（编排/脚本用）。"""
    return PromptCompiler(**kwargs).compile(spec)


def risk_of(spec, **kwargs) -> dict:
    return prescreen_mod.risk_of(spec, **kwargs)
