"""智能组合选择器（Phase 5 升级版）—— 从"最少使用就选"升级为**候选评分器**。

变化（计划 §Phase 5 必做任务 5）：
  · 不再由"谁用得少谁先上"直接定稿，而是先出 10–20 个结构化候选，
    再由 CreativeDirector 按 10 个维度打分 → top3 → 终选（`lib.creative`，与主链同一实现）；
  · 使用次数**没有丢**：它是 Novelty 维度的主特征（用得越多分越低）；
  · 角色组定义从本文件搬到 `lib.creative.cast_groups`，与 Planner 共用一份。

用法:
  python tools/pick_combo.py                       # 16 候选 → 评分 → top3 → 终选
  python tools/pick_combo.py --candidates 12       # 候选数量（10–20）
  python tools/pick_combo.py --group 时尚组 --genre G4 --point shock_18 --angle B20
                                                   # 指定即锁定（评分只作参考）
  python tools/pick_combo.py --commit <tag>        # 记录四池 + 角色组使用（防下条重复）
  python tools/pick_combo.py --json                # 机器可读输出
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles as angles_mod
from lib import genres, products
from lib.creative import CreativeDirector, CreativePlanner, cast_groups
from lib.creative.hotspot import normalize_hotspot
from lib.creative.scoring import SCORE_DIMENSIONS

GROUP_NAMES = tuple(g["name"] for g in cast_groups.GROUP_DEFS)
GENRE_IDS = tuple(g["id"] for g in genres.GENRES)
ANGLE_IDS = tuple(a["id"] for a in angles_mod.ANGLES)
POINT_IDS = tuple(p["id"] for p in products.SALES_POINTS)


def _hotspot(goal: str):
    """借研究库定一个选题；研究库不可用时回退到命令行给的选题（CLI 不阻塞）。"""
    try:
        from lib.creative_research import build_research_brief
        brief = build_research_brief()
        return normalize_hotspot(brief.get("hotspot") or {}), brief
    except Exception:
        return normalize_hotspot({"platform": "cli", "title": goal or "手动选题"}), {}


def _point_name(point_id: str) -> str:
    return next((p["name"] for p in products.SALES_POINTS if p["id"] == point_id), "")


def _genre_name(genre_id: str) -> str:
    return next((g["name"] for g in genres.GENRES if g["id"] == genre_id), "")


def _apply_forced(dna, args) -> list[str]:
    """把命令行指定的池 id 写进候选；返回未通过的校验项（一律打印出来，不静默）。"""
    if args.genre:
        dna.genre = args.genre
    if args.angle:
        dna.angle = args.angle
    if args.point:
        dna.sales_point = args.point
    return dna.validate()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", help=f"角色组（可选: {'/'.join(GROUP_NAMES)}）")
    parser.add_argument("--point", help="指定卖点 id（锁定）")
    parser.add_argument("--angle", help="指定叙事思路 id（锁定）")
    parser.add_argument("--genre", help="指定片型 id（锁定）")
    parser.add_argument("--candidates", type=int, default=16, help="候选数量（10–20）")
    parser.add_argument("--goal", default="", help="选题（研究库不可用时兜底）")
    parser.add_argument("--commit", metavar="TAG", help="记录四池 + 角色组使用（tag=job uid）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    if args.group and args.group not in GROUP_NAMES:
        raise SystemExit(f"未知角色组: {args.group}（可选: {list(GROUP_NAMES)}）")
    for value, pool, label in ((args.genre, GENRE_IDS, "片型"), (args.angle, ANGLE_IDS, "思路"),
                               (args.point, POINT_IDS, "卖点")):
        if value and value not in pool:
            raise SystemExit(f"未知{label}: {value}")

    hotspot, brief = _hotspot(args.goal)
    planner = CreativePlanner(candidate_count=max(10, min(20, args.candidates)))
    candidates = planner.candidates(planner.candidate_count, hotspot=hotspot)

    forced = bool(args.genre or args.angle or args.point)
    if forced:
        dna, structure = candidates[0]
        problems = _apply_forced(dna, args)
        if problems:
            print("  ⚠️ 指定组合未通过校验：" + "；".join(problems))
        candidates = [(dna, structure)]
    if args.group:
        candidates = [(dna, {**structure, "_role_group": args.group})
                      for dna, structure in candidates]

    director = CreativeDirector()
    ranked = director.rank(candidates, context={"trend": hotspot.to_dict(),
                                                "used_counts": planner.used_counts()})
    decision = director.decide(ranked)
    chosen = decision["chosen"]
    group_name = chosen.structure.get("_role_group", "")
    group = cast_groups.pick_group(group_name) if group_name else cast_groups.pick_group()

    if args.json:
        print(json.dumps({"hotspot": hotspot.to_dict(), "forced": forced,
                          "role_group": {"name": group["name"],
                                         "members": cast_groups.group_members(group)},
                          "chosen": chosen.to_dict(), "shortlist": decision["shortlist"],
                          "rule": decision["rule"], "candidate_count": len(ranked)},
                         ensure_ascii=False, indent=1))
    else:
        members = cast_groups.group_members(group)
        print(f"🎯 智能组合（Phase 5 候选评分器｜候选 {len(ranked)} 个 → top3 → 终选）")
        print(f"  选题: {hotspot.title}（source_type={hotspot.source_type}）")
        print(f"  角色组: {group['name']}（{len(members)} 人可选，样例 {', '.join(members[:6])}）")
        print(f"  片型: {chosen.dna.genre} · {_genre_name(chosen.dna.genre)}")
        print(f"  卖点: {chosen.dna.sales_point} · {_point_name(chosen.dna.sales_point)}")
        print(f"  角度: {chosen.dna.angle}")
        print(f"  骨架: {chosen.structure.get('name', '')}"
              f"（{chosen.dna.shot_pattern}｜{chosen.dna.hook_type}｜{chosen.dna.conflict_type}）")
        print(f"  总分: {chosen.total:.3f}")
        for dim in SCORE_DIMENSIONS:
            print(f"    · {dim:<22} {chosen.scores[dim]:.3f}  {chosen.scores['reasons'][dim]}")
        print("  top3：")
        for item in decision["shortlist"]:
            print(f"    - {item['structure_name']}｜{item['dna']['hook_type']}"
                  f"｜{item['dna']['shot_pattern']}  总分 {item['scores']['total']:.3f}")
        print(f"  终选规则: {decision['rule']}")

    if args.commit:
        tag = args.commit
        genres.record_genre(chosen.dna.genre, tag)
        products.record_point(chosen.dna.sales_point, tag)
        angles_mod.record_angle(chosen.dna.angle, tag)
        if group_name:
            cast_groups.record_group(group_name, tag)
        print(f"  ✅ 已记录使用（tag={tag}）：片型/卖点/角度/角色组 各 +1（使用次数=Novelty 特征）")
    if not args.json and not brief:
        print("  ⚠️ 研究库不可用，选题来自命令行兜底")
    return 0


if __name__ == "__main__":
    sys.exit(main())
