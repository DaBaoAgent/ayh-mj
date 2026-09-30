"""Phase 15.4 —— 成片多样性验收（连续规划 ≥10 条 StorySpec）。

计划 §15.4 的硬指标：
  · 不得 10 条全部两人对话；至少 5 种 genre；至少 5 种 hook_type；至少 4 种 shot_pattern；
  · 至少 1 条低对白/无对白方案；
  · 至少 1 条 Vlog/生活流、1 条悬念、1 条实验/对比、1 条喜剧/魔性（或 POV）；
  · 相邻作品不得复用 `genre + hook + angle + cast` 完整组合；
  · 历史相似度超阈值的脚本必须**重新规划**（同一天第二批不得复用第一批的
    骨架签名与选题）。

本文件不新增功能：全部指标都是对 Planner / CreativeDirector 现有输出的验收。
"""
from __future__ import annotations

import pytest

from lib.creative import planner as planner_mod
from lib.jobstore import store as jobstore
from tests import p15_support as S

pytestmark = pytest.mark.integration

GOAL = "Phase15多样性"

# 计划点名的四类片型 → 在 CreativeDNA 各维度上的可接受证据（命中任一即成立）。
# 片型池 id 见 lib/genres.py（G3 魔性广告 / G7 vlog生活流 / G8 反差喜剧 / G9 悬念反转 /
# G10 对比评测）。
NAMED_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "Vlog/生活流": {"genre": ("G7",), "narrative_arc": ("日常纪实",),
                    "shot_pattern": ("五镜生活流",)},
    "悬念": {"genre": ("G9",), "hook_type": ("悬念设问",),
             "shot_pattern": ("悬念三段式",), "narrative_arc": ("悬念揭晓",)},
    "实验/对比": {"genre": ("G10",), "narrative_arc": ("对比实验",),
                  "shot_pattern": ("实验对比双线",)},
    "喜剧/魔性 或 POV": {"genre": ("G3", "G8"),
                         "shot_pattern": ("三镜魔性循环", "POV主观视角", "无对白肢体三段")},
}
LOW_DIALOGUE = ("无对白", "字幕驱动", "画外音旁白")


def _planner(tmp_state) -> planner_mod.CreativePlanner:
    return planner_mod.CreativePlanner(store=jobstore, queue_dir=tmp_state / "queue_15s",
                                       state_dir=tmp_state)


def _docs(planned) -> list[dict]:
    return list(S.planned_docs(planned).values())


def _hits(doc: dict, axes: dict[str, tuple[str, ...]]) -> bool:
    dna = S.doc_dna(doc)
    return any(str(dna.get(key) or "") in values for key, values in axes.items())


def _combo(doc: dict) -> tuple:
    dna = S.doc_dna(doc)
    return tuple(str(dna.get(k) or "") for k in ("genre", "hook_type", "angle", "cast_pattern"))


# ── ① 一次 10 条：全部硬指标 ───────────────────────────────────────────
def test_ten_autonomous_specs_clear_the_diversity_bar(tmp_state):
    planned = planner_mod.plan_missing(store=jobstore, daily_target=10, count=10,
                                       queue_dir=tmp_state / "queue_15s",
                                       state_dir=tmp_state, goal=GOAL)
    assert len(planned) == 10, [p.uid for p in planned]
    docs = _docs(planned)
    assert len(docs) == 10

    stats = S.diversity(docs)
    # 三维结构差异（计划自己的口径是 medium/large 都算"存在结构差异"）
    assert stats["genre"]["count"] >= 5, stats["genre"]
    assert stats["hook_type"]["count"] >= 5, stats["hook_type"]
    assert stats["shot_pattern"]["count"] >= 4, stats["shot_pattern"]

    # 不得 10 条全部为两人对话
    modes = [str(S.doc_dna(d).get("dialogue_mode") or "") for d in docs]
    assert modes.count("双人对白") < len(modes), modes
    assert stats["dialogue_mode"]["count"] >= 3, stats["dialogue_mode"]

    # 至少 1 条低对白 / 无对白方案
    low = [d for d in docs if str(S.doc_dna(d).get("dialogue_mode") or "") in LOW_DIALOGUE]
    assert low, modes

    # 计划点名的四类片型各至少 1 条
    for name, axes in NAMED_PATTERNS.items():
        hits = [i for i, d in enumerate(docs) if _hits(d, axes)]
        assert hits, f"缺少「{name}」方案：{[S.doc_dna(d) for d in docs]}"

    # 同一批 10 条里骨架签名唯一，相邻组合不得完全复刻
    sigs = [tuple(str(S.doc_dna(d).get(k) or "")
                  for k in ("genre", "hook_type", "shot_pattern")) for d in docs]
    assert len(set(sigs)) == len(sigs), sigs
    combos = [_combo(d) for d in docs]
    assert len(set(combos)) == len(combos), combos

    # 每条 spec 的 CreativeDNA 都是完整 20 字段（不是"看着像"的字符串）
    for jour in planned:
        assert not jour.dna.validate(), jour.dna.validate()
        assert jour.dna.signature()


# ── ② 同日第二批：相似度超阈值的脚本被重新规划，而不是复用 ─────────────
def test_second_ten_on_the_same_day_replans_instead_of_reusing_history(tmp_state):
    planner = _planner(tmp_state)
    day = "2026-09-30"
    first = planner.plan_batch(10, goal=GOAL, day=day)
    second = planner.plan_batch(10, goal=GOAL, day=day)
    assert len({j.uid for j in first + second}) == 20, "两批不得撞 uid"

    docs = _docs(first) + _docs(second)
    assert len(docs) == 20
    stats = S.diversity(docs)
    assert stats["genre"]["count"] == 10, stats["genre"]
    assert stats["hook_type"]["count"] >= 5, stats["hook_type"]
    assert stats["shot_pattern"]["count"] >= 4, stats["shot_pattern"]

    def sig(doc: dict) -> tuple:
        dna = S.doc_dna(doc)
        return tuple(str(dna.get(k) or "") for k in ("genre", "hook_type", "shot_pattern"))

    sigs = [sig(d) for d in docs]
    assert len(set(sigs)) == 20, sigs          # 骨架签名：历史命中即重新规划
    hotspots = [str(S.doc_dna(d).get("hotspot") or "") for d in docs]
    assert len(set(hotspots)) == 20, hotspots  # 选题同样不得复用

    # 第二批与第一批零重叠 → 就是"相似度超阈值 → 重新规划"的直接证据
    assert not (set(sigs[:10]) & set(sigs[10:]))
    assert not (set(hotspots[:10]) & set(hotspots[10:]))

    # 相邻作品不得复用 genre+hook+angle+cast 完整组合
    combos = [_combo(d) for d in docs]
    assert len(set(combos)) == 20, combos
    dupes = [i for i, (a, b) in enumerate(zip(combos, combos[1:], strict=False)) if a == b]
    assert dupes == [], dupes
