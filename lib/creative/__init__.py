"""创意规划层（Phase 5）—— 自主选题 → CreativeDNA → 评分 → StorySpec。

对外只暴露这一层；编排器（`stage_plan` / `_plan_batch`）与 CLI（`tools/pick_combo.py`）
都经这里调用，保证"选题 → 创意 → 评分 → StorySpec"只有一套实现，不各写一份。
"""
from .director import CreativeDirector, ScoredDNA
from .dna import CreativeDNA
from .hotspot import NORMALIZED_FIELDS, SOURCE_TYPES, Hotspot, normalize_hotspot
from .planner import CreativePlanner, PlannedJob
from .scoring import DIMENSION_WEIGHTS, SCORE_DIMENSIONS, score_dna
from .storiespec import StorySpec, build_story_spec, summarize_research
from .structures import STORY_STRUCTURES, structure_by_id

__all__ = [
    "CreativeDNA", "Hotspot", "normalize_hotspot", "SOURCE_TYPES", "NORMALIZED_FIELDS",
    "STORY_STRUCTURES", "structure_by_id", "StorySpec", "build_story_spec", "summarize_research",
    "SCORE_DIMENSIONS", "DIMENSION_WEIGHTS", "score_dna",
    "CreativeDirector", "ScoredDNA", "CreativePlanner", "PlannedJob",
]
