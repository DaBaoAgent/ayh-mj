"""学习层（Phase 11）—— 让系统按**本账号自己的**表现越做越聪明。

五个职责（与计划 §Phase 11 一一对应）：
  · `collector`  —— 只读采集 / 导入平台表现（缺失一律 NULL，禁止编造 0）；
  · `normalizer` —— 跨平台指标标准化（逐平台鲁棒百分位）；
  · `features`   —— CreativeDNA 20 个字段全部变成可分析 feature；
  · `scorer`     —— 策略评分：平滑 + 置信度 + 80/20 利用/探索（HistoricalPerformance）；
  · `report`     —— 每日 / 每周复盘（每条结论都带样本量与时间窗口）。

`pipeline` 把它们接成"采集 → 标准化 → 特征 → 学习 → 复盘"一条链，供 Planner 与 CLI 复用。
"""
from __future__ import annotations

from . import collector, features, normalizer, pipeline, report, scorer
from .collector import (
    METRIC_FIELDS,
    CollectionRefused,
    clean_metrics,
    collect_from_store,
    fetch_official,
    import_snapshots,
    load_fixture,
)
from .features import FEATURE_FIELDS, Sample, feature_values, join_samples, load_dna_map
from .normalizer import COMPOSITE_WEIGHTS, MIN_SCALE_N, composite_of, normalize, platform_scales
from .pipeline import (
    LearnedSamples,
    build_samples,
    history_for_planner,
    import_fixture,
    learn_from_store,
    summary_of,
)
from .report import daily_summary, render_markdown, summarize, weekly_summary, write_summary
from .scorer import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    DEFAULT_EXPLOIT_RATIO,
    NO_PREDICTION_NOTE,
    Cell,
    PerformanceModel,
    exploration_pool,
    historical_performance,
    history_hook,
    learn,
    select,
)

__all__ = [
    "collector", "normalizer", "features", "scorer", "report", "pipeline",
    "METRIC_FIELDS", "CollectionRefused", "clean_metrics", "collect_from_store",
    "fetch_official", "import_snapshots", "load_fixture",
    "FEATURE_FIELDS", "Sample", "feature_values", "join_samples", "load_dna_map",
    "COMPOSITE_WEIGHTS", "MIN_SCALE_N", "composite_of", "normalize", "platform_scales",
    "LearnedSamples", "build_samples", "history_for_planner", "import_fixture",
    "learn_from_store", "summary_of",
    "daily_summary", "render_markdown", "summarize", "weekly_summary", "write_summary",
    "CONFIDENCE_HIGH", "CONFIDENCE_LOW", "CONFIDENCE_MEDIUM", "DEFAULT_EXPLOIT_RATIO",
    "NO_PREDICTION_NOTE", "Cell", "PerformanceModel", "exploration_pool",
    "historical_performance", "history_hook", "learn", "select",
]
