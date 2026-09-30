"""策略评分：从**本账号自己的**历史表现做相对策略优化（Phase 11 必做任务 5–9）。

三条不能越界的原则（计划原文）：
  · 任务 6：80% exploitation + 20% exploration，**比例可配**，不是写死的规矩；
  · 任务 7：小样本必须平滑 / 给置信度，不因为一条偶然爆或扑就永久淘汰某片型；
  · 任务 8：**不做"下一条一定爆"的预测承诺**，只做基于历史数据的相对比较。

平滑口径（唯一）：
    smoothed = (n * mean + prior_n * global_mean) / (n + prior_n)
`prior_n` 是伪计数：n 越小 → 越被拉回全局均值 → 一条偶然爆款不会让某片型直接封神。
置信度：n < min_medium → low；n < min_high → medium；否则 high。
**低于 min_medium 的结论一律算 low confidence，并且必须把 n 与时间窗口写进理由。**
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from lib.creative.dna import CreativeDNA

from .features import CATEGORICAL_FIELDS, MULTI_FIELDS, feature_values

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_ORDER = {CONFIDENCE_LOW: 0, CONFIDENCE_MEDIUM: 1, CONFIDENCE_HIGH: 2}

LEARNABLE_FIELDS: tuple[str, ...] = tuple(CATEGORICAL_FIELDS) + tuple(MULTI_FIELDS)

DEFAULT_EXPLOIT_RATIO = 0.8
DEFAULT_PRIOR_N = 5.0
DEFAULT_MIN_MEDIUM = 8
DEFAULT_MIN_HIGH = 30

NO_PREDICTION_NOTE = ("本分数只表示『相对本账号历史分布的更好/更差』，"
                      "不构成『下一条一定爆』的预测；任何结论都可溯到样本量与时间窗口。")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def confidence_for(n: int, *, min_medium: int, min_high: int) -> str:
    if n >= max(1, int(min_high)):
        return CONFIDENCE_HIGH
    if n >= max(1, int(min_medium)):
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


@dataclass
class Cell:
    """某个 (特征, 取值) 的历史表现单元 —— 每条学习结论的最小可追溯单位。"""

    field_name: str
    value: str
    n: int
    mean: float
    smoothed: float
    confidence: str
    window_days: int
    sample_uids: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"field": self.field_name, "value": self.value, "n": self.n,
                "mean": round(self.mean, 4), "smoothed": round(self.smoothed, 4),
                "confidence": self.confidence, "window_days": self.window_days,
                "sample_uids": list(self.sample_uids)}

    def describe(self) -> str:
        return (f"{self.field_name}={self.value}（近 {self.window_days} 天 n={self.n} "
                f"均值 {self.mean:.2f} 平滑 {self.smoothed:.2f}，{self.confidence} 置信）")


@dataclass
class PerformanceModel:
    """一次学习的结果：逐 (特征, 取值) 的表现单元 + 全库基线。"""

    cells: dict = field(default_factory=dict)
    global_mean: float | None = None
    n_samples: int = 0
    window_days: int = 30
    window: dict = field(default_factory=dict)
    platforms: list = field(default_factory=list)
    dropped_uids: list = field(default_factory=list)
    min_medium: int = DEFAULT_MIN_MEDIUM
    min_high: int = DEFAULT_MIN_HIGH

    def cell(self, field_name: str, value: str) -> Cell | None:
        return (self.cells.get(field_name) or {}).get(str(value))

    def confidence(self) -> str:
        return confidence_for(self.n_samples, min_medium=self.min_medium, min_high=self.min_high)

    def low_confidence(self) -> bool:
        return self.confidence() == CONFIDENCE_LOW

    def to_dict(self) -> dict:
        return {
            "n_samples": self.n_samples, "global_mean": (
                round(self.global_mean, 4) if self.global_mean is not None else None),
            "confidence": self.confidence(), "low_confidence": self.low_confidence(),
            "window_days": self.window_days, "window": dict(self.window),
            "platforms": list(self.platforms), "dropped_uids": list(self.dropped_uids),
            "thresholds": {"min_medium": self.min_medium, "min_high": self.min_high},
            "cells": {f: {v: c.to_dict() for v, c in sorted(per.items())}
                      for f, per in sorted(self.cells.items())},
            "note": NO_PREDICTION_NOTE,
        }


def learn(samples, *, window_days: int = 30, prior_n: float = DEFAULT_PRIOR_N,
          min_medium: int = DEFAULT_MIN_MEDIUM, min_high: int = DEFAULT_MIN_HIGH,
          dropped_uids=None) -> PerformanceModel:
    """把样本聚合成 PerformanceModel。没有 composite 的样本不参与统计（不拿 0 顶替）。"""
    usable = [s for s in samples if s.composite is not None]
    model = PerformanceModel(
        n_samples=len(usable), window_days=int(window_days), dropped_uids=list(dropped_uids or []),
        min_medium=int(min_medium), min_high=int(min_high),
        platforms=sorted({str(s.platform) for s in usable}))
    times = sorted(str(s.snapshot_time) for s in usable if s.snapshot_time)
    model.window = {"start": times[0] if times else "", "end": times[-1] if times else "",
                    "days": int(window_days)}
    if not usable:
        return model
    model.global_mean = sum(float(s.composite) for s in usable) / len(usable)

    buckets: dict[str, dict[str, list]] = {}
    for sample in usable:
        for field_name in LEARNABLE_FIELDS:
            for value in sample.values(field_name):
                buckets.setdefault(field_name, {}).setdefault(value, []).append(sample)

    for field_name, per_value in buckets.items():
        cells: dict[str, Cell] = {}
        for value, group in per_value.items():
            scores = [float(s.composite) for s in group]
            n = len(scores)
            mean = sum(scores) / n
            smoothed = ((n * mean + float(prior_n) * model.global_mean)
                        / (n + float(prior_n)))
            cells[value] = Cell(
                field_name=field_name, value=value, n=n, mean=mean,
                smoothed=_clamp(smoothed),
                confidence=confidence_for(n, min_medium=min_medium, min_high=min_high),
                window_days=int(window_days),
                sample_uids=[s.uid for s in group])
        model.cells[field_name] = cells
    return model


def historical_performance(dna: CreativeDNA, model: PerformanceModel | None, *,
                           fields=None) -> dict | None:
    """给一个候选算 HistoricalPerformance。

    · `model` 为空 / 全库 0 条 → None（**没有历史就不假装有**，评分退回原样）；
    · 有历史但该组合一条都没匹配上 → 明确 low confidence，分数取全库均值（不奖不罚），
      这样"全新组合"不会被历史系统判死，探索机会得以保留（任务 5/7）。
    """
    if model is None or model.n_samples == 0 or model.global_mean is None:
        return None
    single, multi = feature_values(dna)
    values = {**single, **multi}
    used: list[Cell] = []
    for field_name in (fields or LEARNABLE_FIELDS):
        raw = values.get(field_name)
        if raw is None or raw == "":
            continue
        items = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for value in items:
            cell = model.cell(field_name, value)
            if cell is not None:
                used.append(cell)
    window = f"近 {model.window_days} 天（{model.window.get('start', '')[:10]}～{model.window.get('end', '')[:10]}）"
    if not used:
        return {
            "score": _clamp(model.global_mean), "n": 0, "confidence": CONFIDENCE_LOW,
            "insufficient": True, "contributions": [],
            "reason": (f"该组合无可比历史（全库仅 {model.n_samples} 条、{window}）→ "
                       f"low confidence，按全库均值 {model.global_mean:.2f} 打分，不奖不罚以保留探索机会")}
    weights = [math.sqrt(cell.n) for cell in used]
    total_w = sum(weights) or 1.0
    score = sum(w * cell.smoothed for w, cell in zip(weights, used, strict=True)) / total_w
    weakest = min((cell.confidence for cell in used), key=lambda c: CONFIDENCE_ORDER[c])
    n_effective = sum(cell.n for cell in used)
    top = sorted(used, key=lambda c: c.n, reverse=True)[:3]
    return {
        "score": _clamp(score), "n": n_effective, "confidence": weakest,
        "insufficient": weakest == CONFIDENCE_LOW, "contributions": [c.to_dict() for c in used],
        "reason": ("历史表现：" + "；".join(c.describe() for c in top)
                   + f"（{window}， weakest 置信 {weakest}）")}


def history_hook(model: PerformanceModel | None):
    """给 `score_dna(context={"history": ...})` 用的回调（无模型时不挂）。"""
    if model is None or model.n_samples == 0:
        return None

    def _hook(dna: CreativeDNA, _structure: dict | None = None) -> dict | None:
        return historical_performance(dna, model)

    return _hook


def exploration_pool(ranked, model: PerformanceModel | None, *, hook=None) -> list:
    """"还有多少东西没被验证过" —— 证据薄弱（无历史或全 low 置信）的候选。

    保留**候选表顺序**（=综合分降序），所以 pool[0] 就是"最值得一试的未知"。
    """
    callback = hook or (lambda dna, _st=None: historical_performance(dna, model))
    out = []
    for item in ranked or []:
        try:
            hp = callback(item.dna, item.structure)
        except Exception:                       # noqa: BLE001 - 单个候选算不出来不应炸整体
            hp = None
        if hp is None or hp.get("insufficient") or hp.get("confidence") == CONFIDENCE_LOW:
            out.append(item)
    return out


def select(ranked, model: PerformanceModel | None, *, ratio: float = DEFAULT_EXPLOIT_RATIO,
           rng: random.Random | None = None, hook=None) -> dict:
    """80/20 的终选：`ratio` 是**利用**概率（可配），其余概率走探索。

    · 无候选 → chosen=None；
    · 利用：取综合分最高（综合分里已经含 HistoricalPerformance 先验）；
    · 探索：取探索池里综合分最高的（"最有希望的未知"）；
    · 探索池为空（所有候选都有足够证据）→ 退回利用，并显式标 `exploration_fallback`。
    """
    items = list(ranked or [])
    if not items:
        return {"chosen": None, "exploited": False, "explored": False, "ratio": float(ratio),
                "exploration_pool": 0, "fallback": False, "reason": "没有候选",
                "model_n": 0, "model_confidence": CONFIDENCE_LOW, "note": NO_PREDICTION_NOTE}
    ratio = _clamp(ratio)
    rng = rng or random.Random(0)
    pool = exploration_pool(items, model, hook=hook)
    best = items[0]
    fallback = False
    if rng.random() < ratio or not pool:
        chosen, explored = best, False
        fallback = not pool
        reason = ("利用（综合分最高；综合分已含 HistoricalPerformance 先验）" if pool
                  else "探索池为空（所有候选都有足够历史证据）→ 退回利用")
    else:
        chosen, explored = pool[0], True
        reason = (f"探索（{len(pool)} 个证据薄弱候选里综合分最高；"
                  f"未知组合要留机会，不能被历史系统判死）")
    return {"chosen": chosen, "exploited": not explored, "explored": explored,
            "ratio": ratio, "exploration_pool": len(pool), "fallback": fallback,
            "reason": reason, "model_n": (model.n_samples if model is not None else 0),
            "model_confidence": (model.confidence() if model is not None else CONFIDENCE_LOW),
            "no_prediction": True, "note": NO_PREDICTION_NOTE}
