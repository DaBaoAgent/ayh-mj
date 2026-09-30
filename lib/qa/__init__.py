"""QA Critic 包（Phase 8）：自动验片 → 明确 error_code → 交给 RepairEngine 定点修复。"""
from .checks import (
    DURATION_TOLERANCE,
    HOOK_MAX_SECONDS,
    MIN_FINAL_BYTES,
    PAYOFF_MAX_RATIO,
    STATIC_MAX_SECONDS,
    SUB_MAX_CHARS_PER_LINE,
    coverage,
    run_checks,
)
from .critic import QaCritic, analyze, critique, evidence_path, gather_evidence, video_path
from .report import DIMENSION_CODES, DIMENSION_LABEL, DIMENSIONS, QaFinding, QaReport

__all__ = [
    "QaCritic", "QaReport", "QaFinding", "analyze", "critique", "gather_evidence",
    "evidence_path", "video_path", "run_checks", "coverage",
    "DIMENSIONS", "DIMENSION_LABEL", "DIMENSION_CODES",
    "MIN_FINAL_BYTES", "DURATION_TOLERANCE", "HOOK_MAX_SECONDS", "STATIC_MAX_SECONDS",
    "PAYOFF_MAX_RATIO", "SUB_MAX_CHARS_PER_LINE",
]
