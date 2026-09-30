"""学习层端到端编排（Phase 11）：采集 → 标准化 → 特征 → 学习 → 复盘。

单独一个模块是为了不让计划点名的五个职责（collector / normalizer / features /
scorer / report）互相 import 成网。这里只做"接线"，不含任何自己的算法口径。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import collector, features, normalizer, report, scorer


@dataclass
class LearnedSamples:
    samples: list = field(default_factory=list)
    dropped_uids: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    scales: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"samples": len(self.samples), "dropped_uids": list(self.dropped_uids),
                "rows": len(self.rows),
                "platforms": sorted({str(s.platform) for s in self.samples})}


def build_samples(root: str | Path, store, *, uid: str | None = None,
                  since: str | None = None, min_n: int = normalizer.MIN_SCALE_N) -> LearnedSamples:
    """本地库 → 学习样本（只读；没有 DNA 的快照会被丢弃并记录 uid）。"""
    rows = collector.collect_from_store(store, uid=uid, since=since)
    if not rows:
        return LearnedSamples()
    normalized, scales = normalizer.normalize(rows, min_n=min_n)
    dna_map = features.load_dna_map(root, uids=[r["uid"] for r in rows])
    samples = features.join_samples(rows, dna_map, normalized=normalized)
    return LearnedSamples(samples=samples, dropped_uids=features.dropped_uids(rows, dna_map),
                          rows=rows, scales=scales)


def learn_from_store(root: str | Path, store, *, day: str = "", window_days: int = 30,
                     prior_n: float = scorer.DEFAULT_PRIOR_N,
                     min_medium: int = scorer.DEFAULT_MIN_MEDIUM,
                     min_high: int = scorer.DEFAULT_MIN_HIGH,
                     uid: str | None = None, since: str | None = None,
                     write: bool = True) -> dict:
    """跑一遍完整学习闭环并（可选）落盘复盘报告。返回复盘 dict（含模型摘要）。"""
    bundle = build_samples(root, store, uid=uid, since=since)
    summary, model = report.build_summary(
        bundle.samples, day=day, window_days=window_days, prior_n=prior_n,
        min_medium=min_medium, min_high=min_high, dropped_uids=bundle.dropped_uids)
    summary["samples"] = bundle.to_dict()
    summary["model"] = model.to_dict()
    if write:
        summary["paths"] = report.write_summary(root, summary, name=f"summary_{day or 'latest'}")
    return summary


def history_for_planner(root: str | Path, store, *, window_days: int = 30,
                        prior_n: float = scorer.DEFAULT_PRIOR_N,
                        min_medium: int = scorer.DEFAULT_MIN_MEDIUM,
                        min_high: int = scorer.DEFAULT_MIN_HIGH):
    """只学模型、不写报告 —— 供 Planner 在规划时取 HistoricalPerformance 先验。"""
    bundle = build_samples(root, store)
    return scorer.learn(bundle.samples, window_days=window_days, prior_n=prior_n,
                        min_medium=min_medium, min_high=min_high,
                        dropped_uids=bundle.dropped_uids)


def import_fixture(root: str | Path, store, path: str | Path, *, dry_run: bool = False) -> dict:
    """从 fixture 导入表现快照（验收用；幂等）。"""
    return collector.import_snapshots(store, collector.load_fixture(path), dry_run=dry_run)


def summary_of(summary: dict) -> str:
    """一行摘要（日志 / 事件用）。"""
    conf = summary.get("confidence")
    return (f"样本 {summary.get('samples_used')}/{summary.get('samples_total')} 条，"
            f"窗口 {summary.get('window_days')} 天，全库均值 "
            f"{summary.get('global_mean') if summary.get('global_mean') is None else round(float(summary['global_mean']), 3)}，"
            f"置信度 {conf}" + ("（数据不足）" if summary.get("low_confidence") else ""))
