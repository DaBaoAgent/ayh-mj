"""Phase 15.1 第 14 条 —— 表现数据回流后 Planner 下一轮评分发生合理变化。

复现口径：fixture 表现数据（`tests/fixtures/learning/`）→ canonical JobStore →
`s7_learn.pipeline.learn_from_store` 产出学习摘要 → **同一个真实 Planner** 在同一批候选上
的评分必须被历史表现改变；下一轮 `plan_for` 落盘的理由里要带着历史模型的样本量，
且方向要朝数据说的那一头走（fixture 里 G1 强、G5 弱）。

全程本地 SQLite + fixture 文件：0 网络、0 付费、不调用任何发布通道。
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from lib.creative import CreativePlanner
from lib.creative.hotspot import normalize_hotspot
from lib.creative.scoring import HISTORICAL_DIMENSION
from lib.jobstore import store
from s7_learn import pipeline, scorer
from tests.p11_support import load_corpus, materialize

pytestmark = pytest.mark.integration

DAY = "2026-09-30"
SPOT = {"platform": "baidu", "title": "老友相聚聊出行", "ref": "assets/trends/热点库.md#L1"}


def _planner(tmp_state) -> CreativePlanner:
    return CreativePlanner(store=store, queue_dir=tmp_state / "queue_15s", state_dir=tmp_state)


def _ranked(path) -> list[dict]:
    return list(json.loads(Path(path).read_text(encoding="utf-8"))["candidates"])


def _reflow(tmp_state) -> dict:
    """把 fixture 表现数据回流进 JobStore 并跑一次学习（返回学习摘要）。"""
    counts = materialize(tmp_state.parent, store, load_corpus())
    assert counts["imported"] == 16 and counts["errors"] == []
    summary = pipeline.learn_from_store(tmp_state.parent, store, day=DAY)
    assert summary["samples"]["samples"] == 15 and summary["low_confidence"] is False
    return summary


def test_same_candidates_are_scored_differently_after_reflow(tmp_state):
    """同一批候选：冷启动没有任何历史维度 → 回流后出现历史维度且总分被改写。"""
    planner = _planner(tmp_state)
    hotspot = normalize_hotspot(SPOT)
    cands = planner.candidates(16, hotspot=hotspot)

    cold = planner.director.rank(cands)
    assert planner.performance_model() is None
    assert all(HISTORICAL_DIMENSION not in c.scores for c in cold), "没有历史时不该伪造历史分"

    _reflow(tmp_state)

    # "下一轮"= 新一次规划（新进程/新实例）：模型按实例记忆，必须新建实例才会重新读历史
    warm_planner = _planner(tmp_state)
    model = warm_planner.performance_model()
    assert model is not None and model.n_samples == 15
    warm = warm_planner.director.rank(cands, context={"history": scorer.history_hook(model),
                                                     "history_weight": 0.25})
    assert all(HISTORICAL_DIMENSION in c.scores for c in warm)
    assert any(abs(a.total - b.total) > 1e-6 for a, b in zip(cold, warm, strict=True)), \
        "回流了历史数据，同一批候选的评分却完全没变"

    # 方向合理性：同一候选换成"历史强片型(G1) / 历史弱片型(G5)"，历史分必须朝数据方向走
    dna, _structure = cands[0]
    strong = scorer.historical_performance(replace(dna, genre="G1"), model, fields=["genre"])
    weak = scorer.historical_performance(replace(dna, genre="G5"), model, fields=["genre"])
    assert strong is not None and weak is not None
    assert strong["score"] > weak["score"]


def test_next_planned_job_carries_the_reflowed_history(tmp_state):
    """下一轮真实规划（plan_for）必须把回流后的历史写进理由与候选评分。"""
    planner = _planner(tmp_state)

    # ① 冷启动：计划理由里明确没有历史模型，候选评分里也没有历史维度
    cold = planner.plan_for("P15LRNCOLD", day=DAY)
    cold_doc = json.loads(Path(cold.dna_path).read_text(encoding="utf-8"))
    assert cold_doc["rationale"]["history"]["model"] is None
    assert all(HISTORICAL_DIMENSION not in c["scores"] for c in _ranked(cold.scores_path))

    # ② 表现数据回流 + 学习
    _reflow(tmp_state)

    # ③ 下一轮（新实例 = 新一次规划）：理由里带样本量，候选评分里带历史维度
    warm_planner = _planner(tmp_state)
    warm = warm_planner.plan_for("P15LRNWARM", day=DAY)
    warm_doc = json.loads(Path(warm.dna_path).read_text(encoding="utf-8"))
    history = warm_doc["rationale"]["history"]
    assert history["model"]["n_samples"] == 15
    assert history["model"]["low_confidence"] is False
    rows = _ranked(warm.scores_path)
    assert rows and all(HISTORICAL_DIMENSION in c["scores"] for c in rows)
    assert rows[0]["scores"][HISTORICAL_DIMENSION] >= rows[-1]["scores"][HISTORICAL_DIMENSION]
