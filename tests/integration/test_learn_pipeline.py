"""Phase 11 集成 —— fixture 表现数据 → 学习闭环 → 复盘（0 网络 0 付费）。

覆盖计划 §Phase 11 验收：
  · 导入一组 fixture 表现数据后，系统可以输出不同 CreativeDNA 的表现差异；
  · Planner 在相同候选下会受到历史数据影响，但仍保留探索候选；
  · 数据不足时明确显示 low confidence。

全程只用本地 SQLite + fixture 文件：不联网、不提交付费任务、不调用任何发布通道。
"""
from __future__ import annotations

import json

import pytest

from lib.creative import CreativePlanner
from lib.creative.hotspot import normalize_hotspot
from lib.creative.scoring import HISTORICAL_DIMENSION
from lib.jobstore import store
from s7_learn import pipeline, report, scorer
from tests.p11_support import CORPUS, flat_snapshots, load_corpus, materialize

pytestmark = pytest.mark.integration

SPOT = {"platform": "baidu", "title": "老友相聚聊出行", "ref": "assets/trends/热点库.md#L1"}


@pytest.fixture(autouse=True)
def _no_real_calls(monkeypatch):
    """自动测试里任何真实付费提交 / 真实发布都必须炸出来（Phase 15 硬约束）。"""
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


def _root(tmp_state):
    return tmp_state.parent


def _learn(tmp_state, **kwargs) -> dict:
    return pipeline.learn_from_store(_root(tmp_state), store, day="2026-09-30", **kwargs)


# ── 验收①：不同 CreativeDNA 的表现差异 ─────────────────────────
def test_fixture_import_then_report_shows_genre_differences(tmp_state):
    counts = materialize(_root(tmp_state), store, load_corpus())
    assert counts["imported"] == 16 and counts["errors"] == []
    summary = _learn(tmp_state)
    assert summary["samples"] == {"samples": 15, "dropped_uids": ["LRN_NODNA_01"],
                                  "rows": 16, "platforms": ["douyin", "xiaohongshu"]}
    assert summary["low_confidence"] is False

    genres = {row["value"]: row for row in summary["distributions"]["genre"]["values"]}
    assert genres["G1"]["n"] == 6 and genres["G5"]["n"] == 6
    assert genres["G1"]["smoothed"] > genres["G5"]["smoothed"], "强片型的平滑分必须更高"
    assert genres["G1"]["mean"] > genres["G5"]["mean"]
    assert genres["G1"]["window_days"] == 30
    assert summary["distributions"]["hook_type"]["values"]


def test_report_lands_under_state_learn_with_both_formats(tmp_state):
    materialize(_root(tmp_state), store, load_corpus())
    summary = _learn(tmp_state)
    json_path = tmp_state / "learn" / "summary_2026-09-30.json"
    md_path = tmp_state / "learn" / "summary_2026-09-30.md"
    assert json_path.is_file() and md_path.is_file()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["samples_used"] == 15
    md = md_path.read_text(encoding="utf-8")
    assert "片型 genre" in md and "钩子 hook" in md
    assert summary["paths"]["json"] == str(json_path)


def test_reimport_is_idempotent_end_to_end(tmp_state):
    materialize(_root(tmp_state), store, load_corpus())
    again = materialize(_root(tmp_state), store, load_corpus())
    assert again["imported"] == 0 and again["skipped"] == 16
    assert len(store.list_performance_metrics()) == 16
    assert _learn(tmp_state)["samples"]["samples"] == 15


# ── 验收③：数据不足 → low confidence ───────────────────────────
def test_thin_fixture_reports_low_confidence(tmp_state):
    snippet = {"day": "2026-09-30", "jobs": load_corpus()["jobs"][:2]}
    materialize(_root(tmp_state), store, snippet)
    summary = _learn(tmp_state)
    assert summary["samples"]["samples"] == 2
    assert summary["low_confidence"] is True and summary["confidence"] == "low"
    md = report.render_markdown(summary)
    assert "low confidence" in md
    assert "不据此淘汰任何片型" in md


# ── 缺失指标不许变 0 ──────────────────────────────────────────
def test_cross_platform_missing_metrics_stay_null(tmp_state):
    materialize(_root(tmp_state), store, load_corpus())
    xhs = store.list_performance_metrics(platform="xiaohongshu")
    assert len(xhs) == 3
    assert all(row["impressions"] is None for row in xhs)
    assert all(row["retention_5s"] is None for row in xhs)
    assert all(row["likes"] is not None for row in xhs)
    bundle = pipeline.build_samples(_root(tmp_state), store)
    xhs_sample = next(s for s in bundle.samples if s.platform == "xiaohongshu")
    assert "completion" in xhs_sample.norm and xhs_sample.norm["impressions"] is None


# ── 验收②：Planner 受历史影响 + 保留探索 ────────────────────────
def test_planner_uses_the_learning_loop_end_to_end(tmp_state):
    materialize(_root(tmp_state), store, load_corpus())
    planner = CreativePlanner(store=store, queue_dir=tmp_state / "queue_15s", state_dir=tmp_state)
    model = planner.performance_model()
    assert model is not None and model.n_samples == 15

    hotspot = normalize_hotspot(SPOT)
    cands = planner.candidates(16, hotspot=hotspot)
    cold = planner.director.rank(cands)
    warm = planner.director.rank(cands, context={"history": scorer.history_hook(model),
                                                 "history_weight": 0.25})
    assert any(HISTORICAL_DIMENSION in c.scores for c in warm)
    assert any(abs(a.total - b.total) > 1e-6 for a, b in zip(cold, warm, strict=True))

    job = planner.plan_for("P11E2E", day="2026-09-30")
    doc = json.loads(job.dna_path.read_text(encoding="utf-8"))
    assert doc["rationale"]["history"]["model"]["n_samples"] == 15
    assert doc["rationale"]["history"]["selection"]["no_prediction"] is True
    assert job.decision["chosen"].dna.genre in [s["dna"]["genre"] for s in job.decision["shortlist"]]
    scores = json.loads(job.scores_path.read_text(encoding="utf-8"))
    ranked = scores["candidates"]
    assert all(HISTORICAL_DIMENSION in c["scores"] for c in ranked)
    assert ranked[0]["scores"][HISTORICAL_DIMENSION] >= ranked[-1]["scores"][HISTORICAL_DIMENSION]


def test_fixture_file_is_the_only_input_and_is_self_describing():
    corpus = load_corpus()
    assert CORPUS.is_file()
    assert len(flat_snapshots(corpus)) == 16
    assert corpus["day"] == "2026-09-30"
    assert "G1 强" in corpus["note"]
