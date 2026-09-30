"""Phase 11 单测 —— 每日 / 每周复盘（计划任务 4/9）。

重点证明：计划点名的六个维度都有分布；**每个数字都带 n 与时间窗口**；
数据不足时显式标 low confidence；报告里没有任何"下一条一定爆"的预测口吻。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.jobstore import store
from s7_learn import pipeline, report
from s7_learn.features import Sample
from tests.p11_support import load_corpus, materialize

pytestmark = pytest.mark.unit

PLAN_NAMED = {"genre", "hook_type", "angle", "sales_point", "cast_pattern", "shot_pattern"}


def _samples(root):
    materialize(root, store, load_corpus())
    return pipeline.build_samples(root, store)


def test_summary_covers_the_six_dimensions_named_in_the_plan(tmp_state):
    bundle = _samples(tmp_state.parent)
    summary, model = report.build_summary(bundle.samples, day="2026-09-30", window_days=30)
    assert set(summary["distributions"]) >= PLAN_NAMED, "计划点名的六个维度一个都不能少"
    assert set(report.SUMMARY_FIELDS) >= PLAN_NAMED
    assert summary["samples_total"] == 15
    assert model.n_samples == 15


def test_every_conclusion_carries_sample_size_and_time_window(tmp_state):
    bundle = _samples(tmp_state.parent)
    summary, _ = report.build_summary(bundle.samples, day="2026-09-30", window_days=30)
    rows = summary["distributions"]["genre"]["values"]
    assert rows, "genre 必须有分布"
    for row in rows:
        assert row["n"] > 0
        assert row["window_days"] == 30
        assert row["confidence"] in {"low", "medium", "high"}
        assert row["mean"] is not None and row["smoothed"] is not None
        assert row["sample_uids"], "每条结论都要能指回样本"

    md = report.render_markdown(summary)
    assert "| 取值 | n | 窗口(天) | 均值 | 平滑 | 置信度 |" in md
    assert "时间窗口：近 30 天" in md
    assert "不构成" in md, "报告必须显式声明不做预测承诺"


def test_markdown_and_json_are_the_same_data(tmp_state):
    bundle = _samples(tmp_state.parent)
    summary, _ = report.build_summary(bundle.samples, day="2026-09-30")
    paths = report.write_summary(tmp_state.parent, summary)
    on_disk = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert on_disk["distributions"].keys() == summary["distributions"].keys()
    md = Path(paths["markdown"]).read_text(encoding="utf-8")
    for row in summary["distributions"]["genre"]["values"]:
        assert row["value"] in md


def test_thin_data_is_reported_as_low_confidence():
    samples = [Sample(uid=f"T{i}", platform="douyin", post_id=None,
                      snapshot_time="2026-09-29T09:00:00", composite=0.5,
                      features={"genre": "G7"}, multi_features={"risk_flags": []})
               for i in range(3)]
    summary, _ = report.build_summary(samples, day="2026-09-30")
    assert summary["low_confidence"] is True
    assert "low confidence" in report.render_markdown(summary)
    assert summary["conclusion_rule"], "必须写明'低样本不据此淘汰片型'"


def test_dropped_samples_are_named_in_the_report(tmp_state):
    bundle = _samples(tmp_state.parent)
    summary, _ = report.build_summary(bundle.samples, day="2026-09-30",
                                      dropped_uids=bundle.dropped_uids)
    assert summary["dropped_uids"] == ["LRN_NODNA_01"]
    assert "丢弃 1 条无 DNA" in report.render_markdown(summary)


def test_daily_and_weekly_summaries_write_to_the_learn_dir(tmp_state):
    bundle = _samples(tmp_state.parent)
    daily = report.daily_summary(bundle.samples, tmp_state.parent, day="2026-09-30")
    assert daily["paths"]["json"].endswith("summary_2026-09-30.json")
    assert (tmp_state / "learn" / "summary_2026-09-30.md").is_file()
    weekly = report.weekly_summary(bundle.samples, tmp_state.parent, week="2026-W40")
    assert (tmp_state / "learn" / "summary_week_2026-W40.json").is_file()
    assert weekly["period"] == "week" and weekly["window_days"] == 7


def test_report_labels_map_field_names_to_the_plan_wording():
    for field_name in PLAN_NAMED:
        assert field_name in report.FIELD_LABELS
    assert "片型" in report.FIELD_LABELS["genre"] and "钩子" in report.FIELD_LABELS["hook_type"]
