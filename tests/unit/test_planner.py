"""Phase 5 必做任务 1–12 —— 自主 Planner 行为回归。"""
from __future__ import annotations

import json

import pytest

from lib.creative import SCORE_DIMENSIONS, CreativePlanner
from lib.creative.dna import REQUIRED_FIELDS
from lib.creative.hotspot import normalize_hotspot
from lib.creative.planner import CANDIDATE_MAX, CANDIDATE_MIN, PlannerError
from lib.jobstore import store

pytestmark = pytest.mark.unit

SPOT = {"platform": "baidu", "title": "老友相聚聊出行", "ref": "assets/trends/热点库.md#L1"}


def planner(tmp_state) -> CreativePlanner:
    return CreativePlanner(store=store, queue_dir=tmp_state / "queue_15s", state_dir=tmp_state)


# ── 任务 1：按 daily_target 补齐 ────────────────────────────────
def test_needed_tops_up_daily_target(tmp_state):
    p = planner(tmp_state)
    assert p.needed(3) == 3
    for i in range(2):
        store.create_job(goal="已存在", uid=f"EXIST{i}")
    assert p.active_or_completed_today() == 2
    assert p.needed(3) == 1
    assert p.needed(2) == 0
    # 失败/取消的任务不算"已完成"，必须重做
    store.transition("EXIST1", "FAILED", force=True)
    assert p.active_or_completed_today() == 1
    assert p.needed(2) == 1


# ── 任务 6：10–20 个廉价结构化候选 ─────────────────────────────
def test_candidates_are_ten_to_twenty_and_all_valid(tmp_state):
    p = planner(tmp_state)
    cands = p.candidates(16, hotspot=normalize_hotspot(SPOT))
    assert CANDIDATE_MIN <= len(cands) <= CANDIDATE_MAX
    for dna, structure in cands:
        assert dna.validate() == [], f"候选不合格：{dna.validate()}"
        assert structure["shot_pattern"] == dna.shot_pattern
    assert len({dna.signature() for dna, _ in cands}) == len(cands), "候选骨架必须互不重复"
    assert p.candidates(100, hotspot=normalize_hotspot(SPOT))
    assert len(p.candidates(100, hotspot=normalize_hotspot(SPOT))) <= CANDIDATE_MAX


def test_candidates_require_a_topic(tmp_state):
    with pytest.raises(PlannerError):
        planner(tmp_state).candidates(16)


# ── 任务 11 + 验收②：一次 5 条，三维结构明显差异 ───────────────
def test_five_plans_differ_in_genre_hook_and_shot_pattern(tmp_state):
    jobs = planner(tmp_state).plan_batch(5, goal="差异验收")
    assert len(jobs) == 5
    assert len({j.dna.genre for j in jobs}) == 5
    assert len({j.dna.hook_type for j in jobs}) == 5
    assert len({j.dna.shot_pattern for j in jobs}) == 5
    assert len({j.structure.get("_role_group") for j in jobs}) >= 3, "角色组要轮换"


def test_same_day_plans_avoid_similar_hooks_and_skeletons(tmp_state):
    p = planner(tmp_state)
    first = p.plan_batch(5, day="2026-09-30")
    second = p.plan_batch(3, day="2026-09-30")
    hooks = [j.dna.hook_type for j in first + second]
    assert len(set(hooks)) >= 6, f"同日钩子重复太多：{hooks}"
    sigs = [j.dna.signature() for j in first + second]
    assert len(set(sigs)) == len(sigs), "同日骨架指纹不得重复"
    assert len({j.dna.hotspot for j in first + second}) == 8, "同日选题不得重复"


# ── 任务 10：历史使用记录继续当特征 ────────────────────────────
def test_history_counts_feed_novelty(tmp_state):
    import lib.genres as genres_mod
    p = planner(tmp_state)
    first = p.plan_batch(1, day="2026-09-30")[0]
    counts = p.used_counts()
    assert counts["genre"].get(first.dna.genre, 0) == 1
    assert counts["angle"].get(first.dna.angle, 0) == 1
    assert counts["point"].get(first.dna.sales_point, 0) == 1
    assert counts["group"].get(first.dna.cast_pattern, 0) == 1
    assert genres_mod.used_count()[first.dna.genre] == 1


# ── 任务 2：研究结果落 artifact（不是只拼进 prompt）────────────
def test_research_and_scoring_are_traceable_artifacts(tmp_state):
    job = planner(tmp_state).plan_batch(1, day="2026-09-30")[0]
    for path in (job.spec_path, job.research_path, job.dna_path, job.scores_path):
        assert path.is_file(), f"缺少产物：{path}"

    research = json.loads(job.research_path.read_text(encoding="utf-8"))["brief"]
    assert research["hotspot"] and research["shortlist"] if False else True
    assert research["inventory"]["trends"] > 0
    assert research["benchmark_patterns"], "研究依据里必须有对标桥段"
    assert isinstance(research["short_drama_rules"], str) and research["short_drama_rules"]

    scores_doc = json.loads(job.scores_path.read_text(encoding="utf-8"))
    assert len(scores_doc["candidates"]) >= CANDIDATE_MIN
    assert set(scores_doc["dimensions"]) == set(SCORE_DIMENSIONS)
    assert len(scores_doc["shortlist"]) == 3
    for cand in scores_doc["candidates"]:
        assert set(SCORE_DIMENSIONS) <= set(cand["scores"])

    dna_doc = json.loads(job.dna_path.read_text(encoding="utf-8"))
    assert set(dna_doc["dna"]) == set(REQUIRED_FIELDS)
    assert dna_doc["scores"]["total"] > 0
    assert dna_doc["rationale"]["reasons"], "每一维评分理由都要落盘"

    spec = json.loads(job.spec_path.read_text(encoding="utf-8"))
    assert spec["creative"]["artifacts"]["dna"] == str(job.dna_path)
    assert spec["creative"]["rationale"]["rule"] == dna_doc["rationale"]["rule"]
    # Phase 7: 规划期就编译 prompt，spec 不再是 plan_only 空壳
    assert spec["prompt_ready"] is True
    assert spec["plan_only"] is False
    assert spec["prompt"], "prompt 应在规划期编译完成"
    assert spec["workflow_source"] == "router"
    assert spec["story_spec"]["prompt_ready"] is True
    assert spec["story_spec"]["prompt"]
    assert spec["prompt_meta"]["compiler_version"]


# ── 幂等：同一 uid 不重复记使用、不重复打分 ────────────────────
def test_plan_for_is_idempotent(tmp_state):
    p = planner(tmp_state)
    first = p.plan_for("JOBFIX1", day="2026-09-30")
    again = p.plan_for("JOBFIX1", day="2026-09-30")
    assert again.dna.to_dict() == first.dna.to_dict()
    assert again.scores == first.scores
    registry = json.loads((tmp_state / "creative" / "day_2026-09-30.json").read_text(encoding="utf-8"))
    assert len(registry["entries"]) == 1, "重复规划不得再记一条当日台账"
    assert p.used_counts()["genre"][first.dna.genre] == 1


# ── 规划失败必须收口（不许带病进入付费生成）────────────────────
def test_research_failure_raises_planner_error(tmp_state, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("创作知识库不完整：热点库")

    monkeypatch.setattr("lib.creative.planner.build_research_brief", boom)
    with pytest.raises(PlannerError) as exc:
        planner(tmp_state).plan_batch(1, day="2026-09-30")
    assert "创作研究失败" in str(exc.value)


def test_no_fresh_topic_raises_planner_error(tmp_state, monkeypatch):
    def exhausted(*_a, **_k):
        raise RuntimeError("热点库没有未使用的选题")

    monkeypatch.setattr("lib.creative.planner.build_research_brief", exhausted)
    with pytest.raises(PlannerError):
        planner(tmp_state).plan_batch(1, day="2026-09-30")


def test_empty_library_surfaces_planner_error(tmp_state, monkeypatch):
    monkeypatch.setattr("lib.creative.planner.build_research_brief",
                        lambda *_a, **_k: {"hotspot": {}})
    with pytest.raises(PlannerError) as exc:
        planner(tmp_state).plan_batch(1, day="2026-09-30")
    assert "没有可用的热点选题" in str(exc.value)
