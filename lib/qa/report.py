"""QA 报告契约（Phase 8）。

Critic 的产物必须是**机器可读**的：每个 FAIL 都带稳定 `error_code`（RepairEngine 只认
这个码），外加一份给人看的 Markdown；禁止出现"只有一句质量不好"的失败。

维度与计划 §Phase 8 的五组一一对应（delivery 是工程完整性，属于机器 Gate 的前置）：

    product / cast / audio / retention / compliance / delivery

报告同时给出 `coverage`：哪些维度真的跑到了证据。没跑到的维度一律记 `skipped`，
**绝不**当成"通过" —— 那是"抽帧给人看"的老毛病。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

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

# 维度（顺序 = 人类报告里的展示顺序）
DIMENSIONS: tuple[str, ...] = ("product", "cast", "audio", "retention", "compliance", "delivery")
DIMENSION_LABEL: dict[str, str] = {
    "product": "视觉产品保真", "cast": "人物与表演", "audio": "音频/对白",
    "retention": "镜头与留存代理指标", "compliance": "品牌/合规", "delivery": "成片完整性",
}
DIMENSION_CODES: dict[str, tuple[str, ...]] = {
    "product": (PRODUCT_DEFORMED,),
    "cast": (HUMAN_ANATOMY_FAIL, WRONG_SPEAKER, VISUAL_QA_FAIL),
    "audio": (ASR_MISMATCH, SUBTITLE_ALIGN_FAIL),
    "retention": (VISUAL_QA_FAIL,),
    "compliance": (COMPLIANCE_BLOCK,),
    "delivery": (QA_FAILED, DOWNLOAD_FAILED),
}

# FAIL / WARN / INFO —— PASS 只用于维度结论，不作为 finding
SEVERITIES: tuple[str, ...] = ("FAIL", "WARN", "INFO")
SEVERITY_WEIGHT = {"FAIL": 0.35, "WARN": 0.10, "INFO": 0.0}

# 一个 job 里多个 FAIL 时，谁决定 RepairEngine 的动作（合规→人工的码优先，
# 免得先烧钱重生一版、再因为文案违规被拦住）
PRIMARY_PRIORITY: tuple[str, ...] = (
    COMPLIANCE_BLOCK, DOWNLOAD_FAILED, PRODUCT_DEFORMED, WRONG_SPEAKER,
    HUMAN_ANATOMY_FAIL, ASR_MISMATCH, SUBTITLE_ALIGN_FAIL, VISUAL_QA_FAIL, QA_FAILED,
)


@dataclass(frozen=True)
class QaFinding:
    """一条 QA 结论。`error_code` 是硬要求 —— 没有它这条 finding 不成立。"""

    dimension: str
    severity: str
    error_code: str
    message: str
    shot: int | None = None
    fix_hint: str = ""
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ValueError(f"未知 QA 维度：{self.dimension}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"未知严重度：{self.severity}")
        if not self.error_code:
            raise ValueError("QA finding 必须带 error_code")

    @property
    def failed(self) -> bool:
        return self.severity == "FAIL"

    def to_dict(self) -> dict:
        return {"dimension": self.dimension, "severity": self.severity,
                "error_code": self.error_code, "message": self.message,
                "shot": self.shot, "fix_hint": self.fix_hint,
                "evidence": dict(self.evidence)}


@dataclass
class QaReport:
    """一次验片的完整结论：结构化 + 人类可读。"""

    uid: str = ""
    stage: str = "qa"
    findings: list[QaFinding] = field(default_factory=list)
    dimensions: dict[str, str] = field(default_factory=dict)   # 维度 → pass/fail/skipped
    coverage: float = 0.0
    notes: list[str] = field(default_factory=list)
    generated_at: str = ""

    # ── 断言面 ────────────────────────────────────────────────
    @property
    def failed(self) -> bool:
        return any(f.failed for f in self.findings)

    @property
    def passed(self) -> bool:
        return not self.failed

    def failures(self) -> list[QaFinding]:
        return [f for f in self.findings if f.failed]

    def warnings(self) -> list[QaFinding]:
        return [f for f in self.findings if f.severity == "WARN"]

    def codes(self) -> list[str]:
        """按优先级排序的 FAIL error_code（去重）。"""
        seen: list[str] = []
        for code in PRIMARY_PRIORITY:
            if any(f.failed and f.error_code == code for f in self.findings):
                seen.append(code)
        for f in self.findings:      # 表外的码（理论上不该有）也带上，不静默吞掉
            if f.failed and f.error_code not in seen:
                seen.append(f.error_code)
        return seen

    def primary_error(self) -> str | None:
        codes = self.codes()
        return codes[0] if codes else None

    def score(self) -> float:
        penalty = sum(SEVERITY_WEIGHT.get(f.severity, 0.0) for f in self.findings)
        return round(max(0.0, 1.0 - penalty), 3)

    def summary(self) -> str:
        fails = len(self.failures())
        warns = len(self.warnings())
        head = f"{'FAIL' if self.failed else 'PASS'}（{fails} FAIL / {warns} WARN）"
        code = self.primary_error()
        return f"{head}｜主错误码 {code}｜覆盖 {self.coverage:.0%}" if code \
            else f"{head}｜覆盖 {self.coverage:.0%}"

    # ── 落盘 ──────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"uid": self.uid, "stage": self.stage, "passed": self.passed,
                "score": self.score(), "coverage": self.coverage,
                "dimensions": dict(self.dimensions),
                "codes": self.codes(), "primary_error": self.primary_error(),
                "summary": self.summary(), "notes": list(self.notes),
                "generated_at": self.generated_at,
                "findings": [f.to_dict() for f in self.findings]}

    def to_json(self, *, indent: int = 1) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        lines = [f"# QA 报告 — {self.uid or '(未命名)'}", "",
                 f"- 结论：**{self.summary()}**",
                 f"- 生成时间：{self.generated_at or datetime.now().isoformat(timespec='seconds')}",
                 "", "| 维度 | 结论 | 说明 |", "|---|---|---|"]
        for dim in DIMENSIONS:
            status = self.dimensions.get(dim, "skipped")
            mark = {"pass": "通过", "fail": "**不通过**", "skipped": "无证据（未检查）"}[status]
            lines.append(f"| {DIMENSION_LABEL[dim]} | {mark} | |")
        if self.notes:
            lines += ["", "## 备注"]
            lines += [f"- {n}" for n in self.notes]
        if self.findings:
            lines += ["", "## 明细（FAIL / WARN 都带 error_code）",
                      "", "| 严重度 | 维度 | error_code | 镜 | 结论 | 修复方向 |",
                      "|---|---|---|---|---|---|"]
            for f in self.findings:
                shot = "" if f.shot is None else str(f.shot)
                lines.append(f"| {f.severity} | {DIMENSION_LABEL[f.dimension]} | `{f.error_code}` "
                             f"| {shot} | {f.message} | {f.fix_hint} |")
        else:
            lines += ["", "没有 FAIL / WARN。"]
        lines.append("")
        return "\n".join(lines)
