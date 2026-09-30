"""创意规划层（Phase 5）—— 自主选题 → CreativeDNA → 评分 → StorySpec。

对外只暴露这一层；编排器（`stage_plan` / `_plan_batch`）与 CLI（`tools/pick_combo.py`）
都经这里调用，保证"选题 → 创意 → 评分 → StorySpec"只有一套实现，不各写一份。

Phase 7 起，`lib/creative` 还负责**编译与路由**（StorySpec → H3 prompt → 工作流链），
所以对外也暴露 compiler / router / prescreen / acting 的公开入口。
"""
from .acting import beat_line, profile_for, role_label
from .acting import blocks as acting_blocks
from .compiler import (
    COMPILER_VERSION,
    CompiledPrompt,
    PromptBudget,
    PromptBudgetExceeded,
    PromptCompiler,
    compile_spec,
    gate_text,
)
from .director import CreativeDirector, ScoredDNA
from .dna import CreativeDNA
from .hotspot import NORMALIZED_FIELDS, SOURCE_TYPES, Hotspot, normalize_hotspot
from .planner import CreativePlanner, PlannedJob
from .prescreen import (
    PRESCREEN_EVAL,
    PRESCREEN_SECONDS,
    build_prescreen_spec,
    needs_prescreen,
    prescreen_passed,
    record_prescreen,
    risk_of,
)
from .scoring import (
    DEFAULT_HISTORY_WEIGHT,
    DIMENSION_WEIGHTS,
    HISTORICAL_DIMENSION,
    SCORE_DIMENSIONS,
    score_dna,
)
from .storiespec import SPEC_VERSION, StorySpec, build_story_spec, summarize_research
from .structures import STORY_STRUCTURES, structure_by_id
from .workflow import (
    MAX_CHAIN,
    Requirement,
    RoutePlan,
    WorkflowIncompatible,
    choose,
    compatible,
    requirements_from_spec,
    route_for_spec,
    validate_chain,
)

__all__ = [
    "CreativeDNA", "Hotspot", "normalize_hotspot", "SOURCE_TYPES", "NORMALIZED_FIELDS",
    "STORY_STRUCTURES", "structure_by_id", "StorySpec", "SPEC_VERSION", "build_story_spec",
    "summarize_research",
    "SCORE_DIMENSIONS", "DIMENSION_WEIGHTS", "score_dna",
    "HISTORICAL_DIMENSION", "DEFAULT_HISTORY_WEIGHT",
    "CreativeDirector", "ScoredDNA", "CreativePlanner", "PlannedJob",
    # Phase 7：编译 / 路由 / 预筛 / 表演
    "PromptCompiler", "CompiledPrompt", "PromptBudget", "PromptBudgetExceeded",
    "COMPILER_VERSION", "compile_spec", "gate_text",
    "Requirement", "RoutePlan", "WorkflowIncompatible", "choose", "compatible",
    "requirements_from_spec", "route_for_spec", "validate_chain", "MAX_CHAIN",
    "risk_of", "needs_prescreen", "build_prescreen_spec", "record_prescreen",
    "prescreen_passed", "PRESCREEN_SECONDS", "PRESCREEN_EVAL",
    "profile_for", "role_label", "acting_blocks", "beat_line",
]
