"""Creative Director（Phase 5 必做任务 7 / 9）。

职责：把 10–20 个廉价候选**结构化评分**，取出 top3（shortlist），再定稿一个最终方案。

选最终方案**不允许**用"第一个未使用"这种顺序法 —— 定稿规则是：
  ① 综合分最高；
  ② 同分先比 Novelty，再比 TrendFit，再比 SalesPointFit；
  ③ 仍同分则按 (片型, 钩子, 镜头结构, 角色组合) 做稳定哈希 tie-break（可复现，不看顺序）。
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field

from .dna import CreativeDNA
from .scoring import SCORE_DIMENSIONS, explain, score_dna

DEFAULT_SHORTLIST = 3
TIE_BREAK_DIMENSIONS = ("Novelty", "TrendFit", "SalesPointFit")

DECISION_RULE = ("综合分最高；同分依次比 " + " > ".join(TIE_BREAK_DIMENSIONS)
                 + "；再同分按骨架指纹稳定哈希（可复现，绝不用'第一个未使用'）")


@dataclass
class ScoredDNA:
    """一个候选的 DNA + 骨架 + 10 维评分。"""

    dna: CreativeDNA
    structure: dict
    scores: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return float(self.scores.get("total") or 0.0)

    def to_dict(self) -> dict:
        return {"dna": self.dna.to_dict(), "structure": self.structure.get("id", ""),
                "structure_name": self.structure.get("name", ""), "scores": dict(self.scores),
                "note": explain(self.scores)}


def _stable_key(scored: ScoredDNA) -> int:
    sig = "|".join(scored.dna.signature()) + "|" + scored.dna.cast_pattern
    return zlib.crc32(sig.encode("utf-8"))


class CreativeDirector:
    """确定性导演：同一批候选 + 同一上下文 → 永远同一个决定。"""

    def __init__(self, *, shortlist_size: int = DEFAULT_SHORTLIST) -> None:
        self.shortlist_size = max(1, int(shortlist_size))

    def rank(self, items: list[tuple[CreativeDNA, dict]], *,
             context: dict | None = None) -> list[ScoredDNA]:
        """给所有候选打分并按综合分降序（同分走 tie-break，结果确定）。

        候选以 `(dna, structure)` 形式给出 —— CreativeDNA 本身不背骨架，
        骨架是"结构"层的对象（见 structures.STORY_STRUCTURES）。
        """
        scored = [ScoredDNA(dna=dna, structure=st, scores=score_dna(dna, structure=st, context=context))
                  for dna, st in items]
        return self._sort(scored)

    def _sort(self, scored: list[ScoredDNA]) -> list[ScoredDNA]:
        def key(item: ScoredDNA):
            return (round(item.total, 6),
                    *[round(float(item.scores.get(d) or 0.0), 6) for d in TIE_BREAK_DIMENSIONS],
                    _stable_key(item))
        return sorted(scored, key=key, reverse=True)

    def shortlist(self, ranked: list[ScoredDNA], *, size: int | None = None) -> list[ScoredDNA]:
        return list(ranked[: max(1, int(size or self.shortlist_size))])

    def decide(self, ranked: list[ScoredDNA], *, size: int | None = None,
               selection: dict | None = None) -> dict:
        """top3 + 终选（终选必定来自 shortlist 的第一名，而不是候选表的第一名）。

        Phase 11 起可传 `selection`（`s7_learn.scorer.select()` 的结果）：它选"探索"时，
        终选就是"最有希望的未知"，并被并入 shortlist —— 保证 TOP3 里始终看得见那条
        探索候选，而不是被历史先验悄悄挤掉（计划任务 5：必须保留探索机会）。
        """
        short = self.shortlist(ranked, size=size)
        chosen = short[0] if short else None
        explored = False
        if selection and selection.get("chosen") is not None:
            picked = selection["chosen"]
            explored = bool(selection.get("explored"))
            if picked is not chosen:
                short = [picked, *[s for s in short if s is not picked]]
                short = short[: max(1, int(size or self.shortlist_size))]
            chosen = picked
        return {
            "rule": DECISION_RULE + ("" if not selection else "；终选另受利用/探索策略约束"),
            "chosen": chosen,
            "shortlist": [s.to_dict() for s in short],
            "candidate_count": len(ranked),
            "dimensions": list(SCORE_DIMENSIONS),
            "explored": explored,
            "exploration": ({k: v for k, v in selection.items() if k != "chosen"}
                            if selection else None),
            "note": explain(chosen.scores) if chosen else "",
            "reasons": dict(chosen.scores.get("reasons") or {}) if chosen else {},
        }
