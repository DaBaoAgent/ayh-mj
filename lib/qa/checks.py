"""QA 维度检查（Phase 8）—— 纯函数：证据 dict 进，`QaFinding` 列表出。

证据是普通 dict（JSON 友好），来源有两种：
  1. 真实产物：`critic.gather_evidence()` 用 ffprobe 探测成片、读字幕/转写 artifact；
  2. fixture / 多模态模型：一份 `qa_evidence_<uid>.json`（自动测试与"看画面"共用同一 schema）。

为什么做成纯函数：Gate 必须可复现、可单测、0 付费。真正的"看画面"由证据里的
`vision` 段承载（Phase 8 由 fixture / 人工或多模态模型回填；Phase 9+ 可接 `media_analysis`），
Critic 只负责**判定 + 路由**，不自己猜画面。
"""
from __future__ import annotations

import re

from ..orchestrator.errors import (
    ASR_MISMATCH,
    COMPLIANCE_BLOCK,
    DOWNLOAD_FAILED,
    HUMAN_ANATOMY_FAIL,
    PRODUCT_DEFORMED,
    QA_FAILED,
    SUBTITLE_ALIGN_FAIL,
    VISUAL_QA_FAIL,
    WRONG_SPEAKER,
)
from .report import DIMENSIONS, QaFinding

# ── 阈值（一处声明；报告与文档都引用这里）──────────────────────────
MIN_FINAL_BYTES = 100_000          # 低于此值视为坏文件（15s 成片实测 >1MB）
DURATION_TOLERANCE = 1.5           # 成片时长与 spec 允许偏差（秒）
HOOK_MAX_SECONDS = 2.0             # 0–2s 必须出现明确钩子
STATIC_MAX_SECONDS = 2.0           # 无意义静止/长停顿上限
PAYOFF_MAX_RATIO = 0.85            # payoff 不得晚于总时长的 85%
SUB_OVERLAP_TOLERANCE = 0.12       # 字幕允许的相邻重叠（秒）
SUB_MAX_CHARS_PER_LINE = 16        # 单行字幕上限（安全区/断句）
# 响度/真峰值阈值与检测实现统一在 lib/post/loudness.py（Phase 9 任务 11），此处只引用，
# 避免「混音口径」与「验片口径」两套数字漂移。
from ..post.loudness import LOUDNESS_BAND, TRUE_PEAK_MAX  # noqa: E402

_SPEECH_MODES = ("dialogue", "duo", "interview", "vlog", "comment", "pov", "voiceover")


# ── 工具 ────────────────────────────────────────────────────────
def _norm(text) -> str:
    """比较用归一：只留中日韩与字母数字（去标点/空白/全角）。"""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", str(text or "")).lower()


def _num(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out


def _shot(value) -> int | None:
    got = _num(value)
    return None if got is None else int(got)


def _speaks(spec: dict) -> bool:
    mode = str(spec.get("dialogue_mode") or "")
    if mode in ("", "silent", "soundscape", "caption"):
        return False
    return any(key in mode for key in _SPEECH_MODES)


def _expected_lines(spec: dict) -> list[dict]:
    return [x for x in (spec.get("expected_lines") or []) if isinstance(x, dict)]


# ── ① 成片完整性（工程 Gate 的前置，不通过就没必要看画面）──────────
def check_delivery(ev: dict) -> list[QaFinding]:
    vid = ev.get("video") or {}
    spec = ev.get("spec") or {}
    out: list[QaFinding] = []
    if not vid.get("exists", False):
        return [QaFinding("delivery", "FAIL", DOWNLOAD_FAILED,
                          "成片文件不存在（provider artifact 可能没下回来）",
                          fix_hint="只重下 provider artifact，不重新生成",
                          evidence=dict(vid))]
    size = int(_num(vid.get("bytes"), 0) or 0)
    if size < MIN_FINAL_BYTES:
        out.append(QaFinding("delivery", "FAIL", QA_FAILED,
                             f"成片疑似损坏（{size} 字节 < {MIN_FINAL_BYTES}）",
                             fix_hint="确认下载完整性；必要时重下再验",
                             evidence={"bytes": size}))
    if int(_num(vid.get("video_streams"), 0) or 0) < 1:
        out.append(QaFinding("delivery", "FAIL", QA_FAILED, "成片没有视频流",
                             fix_hint="重新生成（编码失败）"))
    if _speaks(spec) and int(_num(vid.get("audio_streams"), 0) or 0) < 1:
        out.append(QaFinding("delivery", "FAIL", QA_FAILED,
                             "有对白的片却没有音频流（音轨丢失）",
                             fix_hint="回 generate 重出，或确认 make_15s 的音轨合并没有失败"))
    expected = _num(spec.get("duration"))
    actual = _num(vid.get("duration"))
    if expected and actual is not None and abs(actual - expected) > DURATION_TOLERANCE:
        out.append(QaFinding("delivery", "FAIL", QA_FAILED,
                             f"成片时长 {actual:.2f}s 与 spec {expected:.0f}s 偏差超 "
                             f"{DURATION_TOLERANCE}s",
                             fix_hint="回 compose 重新裁剪/回 generate 重出"))
    loud = _num(vid.get("loudness_lufs"))
    if loud is not None and not (LOUDNESS_BAND[0] <= loud <= LOUDNESS_BAND[1]):
        out.append(QaFinding("delivery", "WARN", QA_FAILED,
                             f"整体响度 {loud:.1f} LUFS 不在 {LOUDNESS_BAND} 目标区间",
                             fix_hint="Phase 9 AudioDirector 统一混音；先人工确认是否压住人声",
                             evidence={"loudness_lufs": loud}))
    peak = _num(vid.get("true_peak_db"))
    if peak is not None and peak > TRUE_PEAK_MAX:
        out.append(QaFinding("delivery", "WARN", QA_FAILED,
                             f"真峰值 {peak:.1f} dBTP 超过 {TRUE_PEAK_MAX}（有削波风险）",
                             fix_hint="限幅后再出", evidence={"true_peak_db": peak}))
    return out


# ── ② 视觉产品保真 ──────────────────────────────────────────────
def check_product(ev: dict) -> list[QaFinding]:
    vis = ev.get("vision")
    if not isinstance(vis, dict):
        return []
    spec = ev.get("spec") or {}
    out: list[QaFinding] = []
    expected = _num(spec.get("products_expected"))
    seen = _num(vis.get("products_seen"))
    if expected is not None and seen is not None and seen != expected:
        out.append(QaFinding("product", "FAIL", PRODUCT_DEFORMED,
                             f"画面产品数 {seen:g} ≠ StorySpec 要求 {expected:g}",
                             fix_hint="锁死产品数量；多余产品必须清场后重生",
                             evidence={"products_seen": seen, "expected": expected}))
    per_shot = vis.get("product_count_per_shot")
    if isinstance(per_shot, list) and len(set(per_shot)) > 1:
        out.append(QaFinding("product", "FAIL", PRODUCT_DEFORMED,
                             f"同一条片内产品数量漂移：{per_shot}",
                             fix_hint="固定机位与道具；重生问题镜",
                             evidence={"product_count_per_shot": list(per_shot)}))
    if vis.get("product_deformed"):
        parts = vis.get("deformed_parts") or []
        out.append(QaFinding("product", "FAIL", PRODUCT_DEFORMED,
                             "产品出现形变" + (f"（{('、'.join(str(p) for p in parts))}）" if parts else ""),
                             fix_hint="简化动作/构图、加强产品 refs，优先重生问题镜",
                             evidence={"deformed_parts": list(parts)}))
    if vis.get("product_color_ok") is False:
        out.append(QaFinding("product", "FAIL", PRODUCT_DEFORMED, "产品颜色/配色与参考图不一致",
                             fix_hint="加强产品单元素材权重后重生"))
    drift = vis.get("product_drift_shots") or []
    if drift:
        out.append(QaFinding("product", "FAIL", PRODUCT_DEFORMED,
                             f"镜 {list(drift)} 出现产品漂移/换车型",
                             shot=_shot(drift[0]), fix_hint="同一条片内不得换车型；重生问题镜",
                             evidence={"product_drift_shots": list(drift)}))
    logo = vis.get("logo_ok")
    if logo is False:
        out.append(QaFinding("product", "FAIL", PRODUCT_DEFORMED, "LOGO/品牌字区域字形错误",
                             fix_hint="保留主体品牌字并改用参考图字形的写法后重生"))
    return out


# ── ③ 人物与表演 ────────────────────────────────────────────────
def check_cast(ev: dict) -> list[QaFinding]:
    vis = ev.get("vision")
    if not isinstance(vis, dict):
        return []
    spec = ev.get("spec") or {}
    out: list[QaFinding] = []
    expected = _num(spec.get("people_expected"))
    seen = _num(vis.get("people_seen"))
    if expected is not None and seen is not None and seen != expected:
        out.append(QaFinding("cast", "FAIL", VISUAL_QA_FAIL,
                             f"画面人数 {seen:g} ≠ StorySpec 要求 {expected:g}",
                             fix_hint="调整 occupancy/机位让人数稳定；重生",
                             evidence={"people_seen": seen, "expected": expected}))
    issues = vis.get("anatomy_issues") or []
    if vis.get("anatomy_ok") is False or issues:
        detail = f"（{'、'.join(str(x) for x in issues)}）" if issues else ""
        out.append(QaFinding("cast", "FAIL", HUMAN_ANATOMY_FAIL,
                             f"人脸/手/脚/腿/身体结构畸形{detail}",
                             fix_hint="调整 occupancy/镜头距离/动作复杂度后重生",
                             evidence={"anatomy_issues": list(issues)}))
    if vis.get("cast_consistent") is False:
        out.append(QaFinding("cast", "FAIL", VISUAL_QA_FAIL,
                             "人物身份/服装/年龄/发型不连续（同一角色前后不像）",
                             fix_hint="加强角色定妆图参考与角色名一致性后重生"))
    wrong = vis.get("wrong_speaker_shots") or []
    if wrong or vis.get("voice_swapped"):
        detail = f"镜 {list(wrong)}" if wrong else "角色音色交换"
        out.append(QaFinding("cast", "FAIL", WRONG_SPEAKER,
                             f"说话人与声音不匹配（{detail}）",
                             shot=_shot(wrong[0]) if wrong else None,
                             fix_hint="强化该镜 speaker lock；必要时减少同镜角色后重生",
                             evidence={"wrong_speaker_shots": list(wrong)}))
    if vis.get("non_speaker_mouth_open") or vis.get("non_speaker_speaks"):
        out.append(QaFinding("cast", "FAIL", WRONG_SPEAKER,
                             "非说话人张嘴/出声（抢话）",
                             fix_hint="写入「其余人不说话、不张嘴」并加强该镜 speaker lock 后重生"))
    return out


# ── ④ 音频/对白 ─────────────────────────────────────────────────
def check_audio(ev: dict) -> list[QaFinding]:
    out: list[QaFinding] = []
    spec = ev.get("spec") or {}
    tr = ev.get("transcript")
    expected = _expected_lines(spec)
    if isinstance(tr, dict):
        heard = _norm(tr.get("text") or "".join(
            str(s.get("text") or "") for s in (tr.get("segments") or [])))
        homophones = [_norm(x) for x in (tr.get("homophones") or [])]
        for line in expected:
            want = _norm(line.get("text"))
            if not want or want in heard:
                continue
            if any(h and (h in want or want in h) for h in homophones):
                out.append(QaFinding("audio", "WARN", ASR_MISMATCH,
                                     f"镜 {line.get('shot')} 疑似同音识别差异（非真实漏词）",
                                     shot=_shot(line.get("shot")),
                                     fix_hint="同音不算漏词；只重建字幕，不重生视频"))
                continue
            out.append(QaFinding("audio", "FAIL", ASR_MISMATCH,
                                 f"镜 {line.get('shot')} 台词未出现/漏词："
                                 f"期望「{line.get('text')}」",
                                 shot=_shot(line.get("shot")),
                                 fix_hint="真实漏词 → 缩句/调整节奏后重生；只错字 → 只重建字幕",
                                 evidence={"expected": line.get("text")}))
        tail = _num(tr.get("tail_silence_seconds"), 0.0) or 0.0
        if tail > STATIC_MAX_SECONDS:
            out.append(QaFinding("audio", "FAIL", ASR_MISMATCH,
                                 f"片尾静默 {tail:.1f}s（长尾静默，白占时长）",
                                 fix_hint="裁掉长尾或补足口播铺满时长"))
        rate = _num(tr.get("rate_cps"))
        band = spec.get("speech_band")
        if rate is not None and isinstance(band, (list, tuple)) and len(band) == 2:
            low, high = _num(band[0], 0.0) or 0.0, _num(band[1], 99.0) or 99.0
            if not (low <= rate <= high):
                out.append(QaFinding("audio", "WARN", ASR_MISMATCH,
                                     f"语速 {rate:.1f} 字/秒 不在本片型 {low:g}–{high:g} 区间",
                                     fix_hint="按片型调整节奏（不同骨架密度要求不同）",
                                     evidence={"rate_cps": rate, "band": list(band)}))
    out.extend(_check_subtitle(ev))
    return out


def _check_subtitle(ev: dict) -> list[QaFinding]:
    sub = ev.get("subtitle")
    if not isinstance(sub, dict):
        return []
    out: list[QaFinding] = []
    cues = [c for c in (sub.get("cues") or []) if isinstance(c, dict)]
    duration = _num((ev.get("video") or {}).get("duration"))
    for i, cue in enumerate(cues):
        start, end = _num(cue.get("start"), 0.0) or 0.0, _num(cue.get("end"), 0.0) or 0.0
        if end <= start:
            out.append(QaFinding("audio", "FAIL", SUBTITLE_ALIGN_FAIL,
                                 f"第 {i + 1} 条字幕时间轴非法（{start}–{end}）",
                                 fix_hint="只重建字幕，不重新生成视频"))
        if duration is not None and end > duration + 0.05:
            out.append(QaFinding("audio", "FAIL", SUBTITLE_ALIGN_FAIL,
                                 f"第 {i + 1} 条字幕越界（结束 {end:.2f}s > 成片 {duration:.2f}s）",
                                 fix_hint="只重建字幕，不重新生成视频"))
        text = str(cue.get("text") or "")
        if len(text) > SUB_MAX_CHARS_PER_LINE and sub.get("wrap_ok") is not True:
            out.append(QaFinding("audio", "FAIL", SUBTITLE_ALIGN_FAIL,
                                 f"第 {i + 1} 条字幕单行 {len(text)} 字，超过安全区 "
                                 f"{SUB_MAX_CHARS_PER_LINE} 字且未断句",
                                 fix_hint="按安全区分行断句后重建字幕"))
        if i and start < (_num(cues[i - 1].get("end"), 0.0) or 0.0) - SUB_OVERLAP_TOLERANCE:
            out.append(QaFinding("audio", "FAIL", SUBTITLE_ALIGN_FAIL,
                                 f"第 {i} 与第 {i + 1} 条字幕重叠",
                                 fix_hint="同一条时间轴重排后重建字幕"))
    if sub.get("safe_area_ok") is False:
        out.append(QaFinding("audio", "FAIL", SUBTITLE_ALIGN_FAIL, "字幕越出安全区",
                             fix_hint="改配置化字号/安全区后重建字幕"))
    if sub.get("orphan_lines"):
        out.append(QaFinding("audio", "WARN", SUBTITLE_ALIGN_FAIL,
                             f"存在孤行/孤字：{sub.get('orphan_lines')}",
                             fix_hint="合并孤行、自然断句"))
    tests = ev.get("spec", {}).get("expected_lines") or []
    if tests and cues:
        cue_text = _norm("".join(str(c.get("text") or "") for c in cues))
        for line in _expected_lines(ev.get("spec") or {}):
            want = _norm(line.get("text"))
            if want and want not in cue_text:
                out.append(QaFinding("audio", "FAIL", SUBTITLE_ALIGN_FAIL,
                                     f"镜 {line.get('shot')} 的字幕与台词不一致",
                                     shot=_shot(line.get("shot")),
                                     fix_hint="字幕必须来自同一 transcript；重排后重建"))
    return out


# ── ⑤ 镜头与留存代理指标 ────────────────────────────────────────
def check_retention(ev: dict) -> list[QaFinding]:
    vis = ev.get("vision")
    if not isinstance(vis, dict):
        return []
    out: list[QaFinding] = []
    hook = _num(vis.get("first_hook_seconds"))
    if hook is None:
        out.append(QaFinding("retention", "WARN", VISUAL_QA_FAIL,
                             "没有提供 0–2s 钩子出现时间（留存首帧无法判定）",
                             fix_hint="补钩子时间戳证据"))
    elif hook > HOOK_MAX_SECONDS:
        out.append(QaFinding("retention", "FAIL", VISUAL_QA_FAIL,
                             f"0–{HOOK_MAX_SECONDS:g}s 没有明确钩子（首个钩子在 {hook:.1f}s）",
                             fix_hint="把冲突/动作/声音钩子提到前 2 秒",
                             evidence={"first_hook_seconds": hook}))
    static = _num(vis.get("static_seconds"))
    tail = _num((ev.get("transcript") or {}).get("tail_silence_seconds"))
    worst = max([x for x in (static, tail) if x is not None] or [0.0])
    if worst > STATIC_MAX_SECONDS:
        out.append(QaFinding("retention", "FAIL", VISUAL_QA_FAIL,
                             f"存在 {worst:.1f}s 无意义静止/长停顿（上限 {STATIC_MAX_SECONDS:g}s）",
                             fix_hint="删静止段或补动作推进",
                             evidence={"static_seconds": static, "tail_silence": tail}))
    if vis.get("subject_too_small"):
        out.append(QaFinding("retention", "FAIL", VISUAL_QA_FAIL, "主体过小/构图失焦",
                             fix_hint="拉近机位或放大主体后重生"))
    focus = _num(vis.get("out_of_focus_seconds"), 0.0) or 0.0
    if focus > STATIC_MAX_SECONDS:
        out.append(QaFinding("retention", "FAIL", VISUAL_QA_FAIL,
                             f"构图失焦累计 {focus:.1f}s", fix_hint="重生问题镜"))
    payoff = _num(vis.get("payoff_seconds"))
    duration = _num((ev.get("video") or {}).get("duration")) or _num((ev.get("spec") or {}).get("duration"))
    if payoff is not None and duration:
        if payoff > duration * PAYOFF_MAX_RATIO:
            out.append(QaFinding("retention", "FAIL", VISUAL_QA_FAIL,
                                 f"payoff {payoff:.1f}s 过晚（>{duration * PAYOFF_MAX_RATIO:.1f}s）",
                                 fix_hint="把 payoff 提前或砍掉前置铺垫",
                                 evidence={"payoff_seconds": payoff, "duration": duration}))
        if payoff <= 0:
            out.append(QaFinding("retention", "FAIL", VISUAL_QA_FAIL,
                                 "前文冲突没有兑现（没有 payoff）",
                                 fix_hint="补 payoff 镜后重生"))
    return out


# ── ⑥ 品牌/合规 ─────────────────────────────────────────────────
def check_compliance(ev: dict) -> list[QaFinding]:
    from ..claims import gate

    out: list[QaFinding] = []
    copy = ev.get("copy")
    chunks: list[str] = []
    if isinstance(copy, dict):
        chunks += [str(copy.get(k) or "") for k in ("title", "description", "spoken", "on_screen")]
    elif copy:
        chunks.append(str(copy))
    tr = ev.get("transcript")
    if isinstance(tr, dict):
        chunks.append(str(tr.get("text") or ""))
        chunks += [str(c.get("text") or "") for c in (tr.get("segments") or [])]
    text = "\n".join(x for x in chunks if x.strip())
    if text.strip():
        result = gate(text, channel=str(ev.get("channel") or ""))
        for item in result.unmapped:
            out.append(QaFinding("compliance", "FAIL", COMPLIANCE_BLOCK,
                                 f"未登记的产品承诺「{item.text}」",
                                 fix_hint="改文案或补 claim 后再出，不允许绕过 gate",
                                 evidence={"kind": item.kind, "claim_id": None}))
        for item in result.blocked:
            out.append(QaFinding("compliance", "FAIL", COMPLIANCE_BLOCK,
                                 f"claim「{item.claim_id}」当前不可用：{item.blocked_reason or '被禁止'}",
                                 fix_hint="改文案/claim，不允许绕过 gate",
                                 evidence={"kind": item.kind, "claim_id": item.claim_id}))
    if ev.get("ai_generated") is True and not ev.get("ai_disclosure_recorded"):
        out.append(QaFinding("compliance", "FAIL", COMPLIANCE_BLOCK,
                             "AI 生成内容声明未记录（发布 Gate 的硬字段）",
                             fix_hint="补齐 ai_disclosure 记录后再进入发布链路"))
    return out


# ── 汇总 ────────────────────────────────────────────────────────
_CHECKERS = {
    "delivery": check_delivery,
    "product": check_product,
    "cast": check_cast,
    "audio": check_audio,
    "retention": check_retention,
    "compliance": check_compliance,
}
# 该维度需要哪些证据段才算"真的检查过"（缺了 → skipped，绝不算 pass）
_REQUIRES = {
    "product": ("vision",), "cast": ("vision",),
    "audio": ("transcript", "subtitle"), "retention": ("vision",),
    "compliance": ("copy", "transcript"),
}


def _available(dim: str, ev: dict) -> bool:
    keys = _REQUIRES.get(dim)
    if not keys:
        return True
    return any(ev.get(k) for k in keys)


def run_checks(ev: dict, *, dimensions: tuple[str, ...] | None = None
               ) -> tuple[list[QaFinding], dict[str, str], list[str]]:
    """跑指定维度（默认全部），返回 (findings, 维度结论, 备注)。

    调用点按"这一步修得动什么"裁剪维度：生成后验画面/文案（gen），合成后验
    字幕/成片完整性（final）—— 见 `critic.PHASE_DIMENSIONS`。
    """
    findings: list[QaFinding] = []
    dims: dict[str, str] = {}
    notes: list[str] = []
    for dim in (dimensions or DIMENSIONS):
        if dim not in DIMENSIONS:
            raise ValueError(f"未知 QA 维度：{dim}")
        if not _available(dim, ev):
            dims[dim] = "skipped"
            notes.append(f"{dim}：没有可用证据，本次未检查（不算通过）")
            continue
        got = _CHECKERS[dim](ev)
        findings.extend(got)
        dims[dim] = "fail" if any(f.failed for f in got) else "pass"
    if not (ev.get("vision") or {}).get("source") and dims.get("product") == "skipped":
        notes.append("vision 证据缺失：画面类维度（产品/人物/留存）需要 qa_evidence_<uid>.json "
                     "或 Phase 9+ 的画面分析接入")
    return findings, dims, notes


def coverage(dims: dict[str, str]) -> float:
    if not dims:
        return 0.0
    checked = sum(1 for v in dims.values() if v != "skipped")
    return round(checked / len(dims), 3)
