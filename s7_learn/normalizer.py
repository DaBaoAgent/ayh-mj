"""跨平台指标标准化（Phase 11 必做任务 1 / 7）。

为什么必须标准化：抖音的 completion 与 YouTube 的 completion 不是同一个分布，
原始点赞数更是完全不可比（一条 1 万赞的公众号贴 vs 一条 300 赞的 B 站贴）。
本模块把**每个平台的每个指标**先转成"相对该平台自己历史分布的鲁棒百分位"，再加权合成
一个 0..1 的综合表现分。

两条不可退让的规则：
  · **缺失 ≠ 0**：只有 `value is not None` 的指标参与百分位与合成；
    综合分是"在**实际存在**的指标上按权重重新归一"，而不是拿 0 填空再平均。
  · 样本太少的平台**不产出百分位**（`n < min_scale_n`）→ 该平台指标全部为 None，
    交给上层显式报 low confidence，而不是用 2 个样本算出"高置信"。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .collector import METRIC_FIELDS

# 综合分权重：留存/完播是"内容好不好"的主证据，互动是次证据，触达只是分母。
COMPOSITE_WEIGHTS: dict[str, float] = {
    "completion": 0.20, "avg_watch_pct": 0.20, "retention_5s": 0.15,
    "saves": 0.10, "shares": 0.10, "follows": 0.10,
    "comments": 0.05, "likes": 0.05, "views": 0.05,
}

MIN_SCALE_N = 3          # 少于 3 条不给百分位（避免用 1–2 个样本编造"高置信"）


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _percentile(sorted_values: list[float], q: float) -> float:
    """线性插值百分位（q ∈ 0..1）。输入必须已排序且非空。"""
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo]) * (1 - frac) + float(sorted_values[hi]) * frac


def available_metrics(row: dict) -> dict:
    """只取**确实存在**的指标（缺失字段是"没有"，不是 0）。"""
    metrics = row.get("metrics") or {}
    return {k: float(v) for k, v in metrics.items()
            if k in METRIC_FIELDS and v is not None and v != ""}


@dataclass
class Scale:
    """某平台某指标的参照分布（p10/p90 之间做线性映射，抗离群值）。"""

    platform: str
    metric: str
    n: int
    p10: float
    median: float
    p90: float

    def pct(self, value: float | None) -> float | None:
        if value is None:
            return None
        span = self.p90 - self.p10
        if span <= 0:
            return 0.5
        return _clamp((float(value) - self.p10) / span)

    def to_dict(self) -> dict:
        return {"platform": self.platform, "metric": self.metric, "n": self.n,
                "p10": round(self.p10, 4), "median": round(self.median, 4),
                "p90": round(self.p90, 4)}


@dataclass
class NormalizedRow:
    uid: str
    platform: str
    post_id: str | None
    snapshot_time: str
    metrics: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    norm: dict = field(default_factory=dict)
    composite: float | None = None
    scale_n: int = 0

    def to_dict(self) -> dict:
        return {"uid": self.uid, "platform": self.platform, "post_id": self.post_id,
                "snapshot_time": self.snapshot_time, "metrics": dict(self.metrics),
                "missing": list(self.missing), "norm": dict(self.norm),
                "composite": (round(self.composite, 4) if self.composite is not None else None),
                "scale_n": self.scale_n}


def platform_scales(rows: list[dict], *, min_n: int = MIN_SCALE_N) -> dict[str, dict[str, Scale]]:
    """逐平台算参照分布；样本不足的平台**不产出** Scale（不猜）。"""
    grouped: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        platform = str(row.get("platform") or "")
        values = available_metrics(row)
        for metric, value in values.items():
            grouped.setdefault(platform, {}).setdefault(metric, []).append(float(value))
    scales: dict[str, dict[str, Scale]] = {}
    for platform, per_metric in grouped.items():
        out: dict[str, Scale] = {}
        for metric, raw_values in per_metric.items():
            if len(raw_values) < max(1, int(min_n)):
                continue
            values = sorted(raw_values)
            out[metric] = Scale(platform=platform, metric=metric, n=len(values),
                                p10=_percentile(values, 0.10),
                                median=_percentile(values, 0.50),
                                p90=_percentile(values, 0.90))
        scales[platform] = out
    return scales


def composite_of(norm: dict) -> tuple[float | None, float]:
    """按权重在**存在**的维度上重新归一 → (综合分 | None, 实际权重和)。

    一个指标都没有 → None（不是 0）："没数据"和"表现极差"必须能区分开。
    """
    total_w = 0.0
    acc = 0.0
    for metric, weight in COMPOSITE_WEIGHTS.items():
        pct = norm.get(metric)
        if pct is None:
            continue
        acc += weight * float(pct)
        total_w += weight
    if total_w <= 0:
        return None, 0.0
    return _clamp(acc / total_w), total_w


def normalize_row(row: dict, scales: dict[str, dict[str, Scale]]) -> NormalizedRow:
    metrics = available_metrics(row)
    per_platform = scales.get(str(row.get("platform") or ""), {})
    norm: dict = {}
    for metric in METRIC_FIELDS:
        scale = per_platform.get(metric)
        norm[metric] = (scale.pct(metrics.get(metric)) if scale is not None else None)
    value, _ = composite_of(norm)
    return NormalizedRow(
        uid=str(row.get("uid") or ""), platform=str(row.get("platform") or ""),
        post_id=row.get("post_id"), snapshot_time=str(row.get("snapshot_time") or ""),
        metrics=metrics, missing=[f for f in METRIC_FIELDS if f not in metrics],
        norm=norm, composite=value,
        scale_n=max([s.n for s in per_platform.values()] or [0]))


def normalize(rows: list[dict], *, min_n: int = MIN_SCALE_N) -> tuple[list[NormalizedRow], dict]:
    """→ (标准化后的行, 平台参照分布)。参照分布一并返回，供报告说明"凭什么这么比"。"""
    scales = platform_scales(rows, min_n=min_n)
    return [normalize_row(r, scales) for r in rows], scales
