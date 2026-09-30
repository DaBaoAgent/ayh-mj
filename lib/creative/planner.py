"""自主 Planner（Phase 5 必做任务 1–12）。

一句话：**空队列点 Start，系统自己选题、自己出创意、自己打分定稿、自己写出 StorySpec。**

流程（每个 job 一遍）：
  1. `needed()` 按 `daily_target - 今日已存在/已完成` 补齐需要创建的 job 数（任务 1）；
  2. `build_research_brief()` 取研究依据并**整份落 artifact**（任务 2：不只是拼 prompt）；
  3. 热点过 `normalize_hotspot()`，标 `source_type`，常青素材不许冒充实时热点（任务 3/4）；
  4. 生成 10–20 个**廉价结构化** CreativeDNA 候选（任务 6，全程不付费）；
  5. CreativeDirector 10 维评分 → top3 → 终选（任务 7/8/9）；
  6. 历史 used_ideas / 角度 / 片型 / 角色使用记录继续当特征（任务 10）；
  7. 同日相似 hook / 同骨架 / 同角色组合被硬性排除（任务 11）；
  8. 输出明确 `StorySpec`（任务 12），**不**直接吐 H3 大 prompt。

产物（全部可追溯，出片后仍能回答"为什么是这个选题"）：
  `state/queue_15s/<uid>.json`            队列 spec（StorySpec payload）
  `state/creative/research_<uid>.json`    研究依据全文
  `state/creative/dna_<uid>.json`         定稿 CreativeDNA + 骨架 + 评分 + 逐维理由
  `state/creative/scores_<uid>.json`      全部候选与评分（含 top3 与终选规则）
  `state/creative/day_<YYYY-MM-DD>.json`  当日规划台账（同日去重的事实来源）
"""
from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import STATE_DIR
from .. import angles as angles_mod
from .. import genres as genres_mod
from .. import ideas as ideas_mod
from .. import products as products_mod
from ..creative_research import build_research_brief
from . import cast_groups
from .director import CreativeDirector
from .dna import AUDIENCES, CLAIM_RISK_FLAG, GOALS, VISUAL_MOTIFS, CreativeDNA
from .hotspot import normalize_hotspot
from .scoring import NUMERIC_CLAIM_POINTS, STRUCTURE_AUDIENCES
from .storiespec import build_story_spec, summarize_research
from .structures import STORY_STRUCTURES

ROOT = Path(__file__).resolve().parent.parent.parent
DAY_FMT = "%Y-%m-%d"
CANDIDATE_MIN, CANDIDATE_MAX = 10, 20
MAX_ATTEMPTS = 800
EVERGREEN_RISK = "热点为常青素材，时效性弱"
SILENT_RISK = "无对白需字幕/音效兜底"

CTA_LINES: tuple[str, ...] = (
    "评论区扣 1，帮你算算家里老人用不用得上",
    "想要同款细节的，评论区留言「轻便」",
    "点个关注，下一条拍你家门口那段坡",
    "有疑问直接评论，下一条视频现场回答",
    "先收藏，给爸妈看之前自己先看一遍",
)


class PlannerError(RuntimeError):
    """规划失败（研究库缺失 / 候选耗尽 / 写盘失败）。

    必须**阻断**后续付费阶段：调用方（编排器）收到即终止，绝不进入 GENERATING。
    """


@dataclass
class PlannedJob:
    """一次规划的全部产物（DNA / 研究 / 评分 / StorySpec / 落盘路径）。"""

    uid: str
    index: int
    day: str
    dna: CreativeDNA
    structure: dict = field(default_factory=dict)
    hotspot: dict = field(default_factory=dict)
    research: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    shortlist: list = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    spec_path: Path | None = None
    research_path: Path | None = None
    dna_path: Path | None = None
    scores_path: Path | None = None
    message: str = ""

    def artifacts(self) -> list[dict]:
        """登记进 JobStore 的 artifact 清单（顺序即展示顺序）。"""
        out = [{"type": "spec", "path": str(self.spec_path)}] if self.spec_path else []
        for type_, path in (("research", self.research_path),
                            ("creative_dna", self.dna_path),
                            ("creative_scores", self.scores_path)):
            if path:
                out.append({"type": type_, "path": str(path)})
        return out

    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "index": self.index, "day": self.day,
            "dna": self.dna.to_dict(), "structure": self.structure.get("id", ""),
            "hotspot": dict(self.hotspot), "scores": dict(self.scores),
            "shortlist": list(self.shortlist), "decision": dict(self.decision),
            "spec_path": str(self.spec_path or ""), "research_path": str(self.research_path or ""),
            "dna_path": str(self.dna_path or ""), "scores_path": str(self.scores_path or ""),
            "message": self.message,
        }


class CreativePlanner:
    """自主选题 / 创意规划器（唯一实现）。"""

    def __init__(self, *, queue_dir: Path | str | None = None,
                 state_dir: Path | str | None = None, store=None,
                 director: CreativeDirector | None = None,
                 candidate_count: int = 16, seed: str = "",
                 now: datetime | None = None) -> None:
        self.state_dir = Path(state_dir) if state_dir else Path(STATE_DIR)
        self.queue_dir = Path(queue_dir) if queue_dir else self.state_dir / "queue_15s"
        self.creative_dir = self.state_dir / "creative"
        self.store = store
        self.director = director or CreativeDirector()
        self.candidate_count = max(CANDIDATE_MIN, min(CANDIDATE_MAX, int(candidate_count)))
        self.seed = str(seed or "")
        self._now = now

    # ── 时间 / 今日已存在任务 ──────────────────────────────────
    def now(self) -> datetime:
        return self._now or datetime.now()

    def today(self, now: datetime | None = None) -> str:
        return (now or self.now()).strftime(DAY_FMT)

    def active_or_completed_today(self, *, day: str | None = None) -> int:
        """今日"在跑或已完成"的 job 数（FAILED / CANCELLED 不算——那些要重做）。"""
        store = self.store
        if store is None:
            from ..jobstore import store as default_store
            store = default_store
        day = day or self.today()
        alive = {"FAILED", "CANCELLED"}
        count = 0
        for job in store.list_jobs(limit=500):
            created = str(job.get("created_at") or "")[:10]
            if created == day and str(job.get("status") or "").upper() not in alive:
                count += 1
        return count

    def needed(self, daily_target: int, *, day: str | None = None) -> int:
        """还需要创建多少条 = daily_target - 今日已存在/已完成（任务 1）。"""
        return max(0, int(daily_target) - self.active_or_completed_today(day=day))

    # ── 候选生成 ───────────────────────────────────────────────
    def candidates(self, count: int | None = None, *, registry: dict | None = None,
                   hotspot=None) -> list[tuple[CreativeDNA, dict]]:
        """生成 10–20 个廉价结构化候选（每个 = (CreativeDNA, 骨架)）。"""
        n = max(CANDIDATE_MIN, min(CANDIDATE_MAX, int(count or self.candidate_count)))
        used = self.used_counts()
        lists = self._registry_lists(registry or {})
        used_sigs = set(lists["signatures"])
        used_hooks = set(lists["hooks"])
        trend = hotspot.to_dict() if hotspot is not None else {}
        if not trend.get("title"):
            raise PlannerError("候选生成必须先定选题：请先用 build_research_brief + "
                               "normalize_hotspot 得到 hotspot 再生成候选")

        genres_ordered = sorted(genres_mod.GENRES,
                                key=lambda g: (int(used["genre"].get(g["id"], 0)), g["id"]))
        angles_ordered = [a for a in angles_mod.ANGLES if not a.get("used_up")]
        angles_ordered.sort(key=lambda a: (int(used["angle"].get(a["id"], 0)), a["id"]))
        if not angles_ordered:
            raise PlannerError("叙事角度池已耗尽：请先扩充 lib/angles.py 的 ANGLES 再规划")
        points_ordered = sorted(products_mod.SALES_POINTS,
                                key=lambda p: (int(used["point"].get(p["id"], 0)), p["id"]))
        groups_ordered = sorted(cast_groups.GROUP_DEFS,
                                key=lambda g: (int(used["role_group"].get(g["name"], 0)), g["name"]))

        offset = self._offset()
        out: list[tuple[CreativeDNA, dict]] = []
        seen: set = set()
        attempt = 0
        while len(out) < n and attempt < MAX_ATTEMPTS:
            i = attempt
            attempt += 1
            layer = i // len(STORY_STRUCTURES)
            structure = dict(STORY_STRUCTURES[(i + offset) % len(STORY_STRUCTURES)])
            genre = genres_ordered[(layer + i) % len(genres_ordered)]
            angle = angles_ordered[(layer * 3 + i) % len(angles_ordered)]
            point = points_ordered[(layer * 5 + i) % len(points_ordered)]
            group = groups_ordered[(layer + i) % len(groups_ordered)]
            hook = self._pick_hook(structure, used_hooks, layer)
            sig = (genre["id"], hook, structure["shot_pattern"])
            if sig in seen or sig in used_sigs:
                continue
            seen.add(sig)
            structure["_role_group"] = group["name"]
            dna = self._build_dna(structure, genre=genre, angle=angle, point=point, hook=hook,
                                  trend=trend, layer=layer, index=i)
            if dna.validate():
                continue
            out.append((dna, structure))
        if not out:
            raise PlannerError("没有可用候选：同日结构/钩子/角色组合已被占满，请降低今日目标或扩充素材池")
        return out

    def _pick_hook(self, structure: dict, used_hooks: set[str], layer: int) -> str:
        hooks = list(structure.get("hook_types") or ())
        if not hooks:
            return "痛点共鸣"
        for k in range(len(hooks)):
            candidate = hooks[(layer + k) % len(hooks)]
            if candidate not in used_hooks:
                return candidate
        return hooks[layer % len(hooks)]

    def _build_dna(self, structure: dict, *, genre: dict, angle: dict, point: dict,
                   hook: str, trend: dict, layer: int, index: int) -> CreativeDNA:
        audience_pool = STRUCTURE_AUDIENCES.get(structure["id"], AUDIENCES)
        audience = audience_pool[layer % len(audience_pool)]
        motif = (structure.get("visual_motif") if index % 2 == 0
                 else VISUAL_MOTIFS[(index + layer) % len(VISUAL_MOTIFS)])
        risks: list[str] = []
        if point["id"] in NUMERIC_CLAIM_POINTS:
            risks.append(CLAIM_RISK_FLAG)
        if trend.get("source_type") != "live":
            risks.append(EVERGREEN_RISK)
        if structure.get("dialogue_mode") == "无对白":
            risks.append(SILENT_RISK)
        return CreativeDNA(
            audience=audience, goal=GOALS[index % len(GOALS)], hotspot=str(trend.get("title") or ""),
            genre=genre["id"], angle=angle["id"], sales_point=point["id"], hook_type=hook,
            narrative_arc=structure["narrative_arc"], shot_pattern=structure["shot_pattern"],
            cast_pattern=structure["cast_pattern"], product_role=structure["product_role"],
            conflict_type=structure["conflict_type"], visual_motif=motif,
            camera_language=structure["camera_language"], dialogue_mode=structure["dialogue_mode"],
            audio_mode=structure["audio_mode"],
            payoff=f"{point['hook']}｜{structure['name']}把它收在{point['name']}上",
            ending=f"{structure['narrative_arc']}收尾，停在{audience}最在意的那一下",
            CTA=CTA_LINES[(layer + index) % len(CTA_LINES)],
            risk_flags=risks,
        )

    def _offset(self) -> int:
        if not self.seed:
            return 0
        return sum(self.seed.encode("utf-8")) % max(1, len(STORY_STRUCTURES))

    # ── 使用记录（novelty 特征，任务 10）────────────────────────
    def used_counts(self) -> dict:
        return {
            "genre": genres_mod.used_count(),
            "angle": angles_mod.use_counts(),
            "point": products_mod.use_counts(),
            "group": self._registry_counts("cast"),
            "structure": self._registry_counts("structure"),
            "role_group": cast_groups.use_counts(),
        }

    # ── 规划一个 job ───────────────────────────────────────────
    def plan_for(self, uid: str, *, index: int = 0, goal: str = "", day: str | None = None,
                 force: bool = False) -> PlannedJob:
        day = day or self.today()
        if not force:
            existing = self.load_planned(uid)
            if existing is not None:
                return existing
        registry = self._load_registry(day)
        exclude_titles = set(self._registry_lists(registry)["hotspots"]) | set(ideas_mod.used_hotspots())
        try:
            brief = build_research_brief(exclude_titles=exclude_titles)
        except Exception as exc:      # 研究库缺失 / 选题耗尽 → 规划失败（不进付费生成）
            raise PlannerError(f"创作研究失败：{type(exc).__name__}: {exc}") from exc
        hotspot = normalize_hotspot(brief.get("hotspot") or {}, now=self.now())
        if not hotspot.title:
            raise PlannerError("研究结果没有可用的热点选题")

        cands = self.candidates(self.candidate_count, registry=registry, hotspot=hotspot)
        context = {"used_counts": self.used_counts(), "day_registry": self._registry_lists(registry),
                   "trend": hotspot.to_dict(), "claim_points": sorted(NUMERIC_CLAIM_POINTS)}
        ranked = self.director.rank(cands, context=context)
        decision = self.director.decide(ranked)
        chosen = decision["chosen"]
        if chosen is None:
            raise PlannerError("候选评分没有产生终选方案")
        dna: CreativeDNA = chosen.dna
        structure = chosen.structure

        title = self._title(dna, structure, hotspot)
        rationale = {
            "rule": decision["rule"], "note": decision["note"],
            "totals": {s.to_dict()["structure"]: s.total for s in ranked[:5]},
            "reasons": dict(decision.get("reasons") or {}),
            "candidate_count": len(ranked),
        }
        spec = build_story_spec(uid=uid, structure=structure, dna=dna, hotspot=hotspot.to_dict(),
                                research_refs=summarize_research(brief), rationale=rationale,
                                title=title)
        paths = self._paths(uid)
        self._write_json(paths["research"], {"uid": uid, "day": day, "brief": brief})
        self._write_json(paths["dna"], {"uid": uid, "day": day, "structure": structure["id"],
                                        "structure_name": structure["name"],
                                        "role_group": structure.get("_role_group", ""),
                                        "dna": dna.to_dict(), "hotspot": hotspot.to_dict(),
                                        "scores": dict(chosen.scores), "rationale": rationale})
        self._write_json(paths["scores"], {
            "uid": uid, "day": day, "dimensions": decision["dimensions"], "rule": decision["rule"],
            "candidates": [s.to_dict() for s in ranked],
            "shortlist": decision["shortlist"],
            "decision": {"structure": structure["id"], "hook_type": dna.hook_type,
                         "shot_pattern": dna.shot_pattern, "genre": dna.genre,
                         "note": decision["note"]},
        })
        spec.creative_paths = {k: str(v) for k, v in paths.items()}
        self._write_json(paths["spec"], spec.to_spec_json())

        self._record_usage(dna, structure, uid)
        registry = self._append_registry(registry, uid=uid, dna=dna, structure=structure, day=day)
        self._save_registry(day, registry)

        return PlannedJob(
            uid=uid, index=index, day=day, dna=dna, structure=structure,
            hotspot=hotspot.to_dict(), research=brief, scores=dict(chosen.scores),
            shortlist=decision["shortlist"], decision=decision, spec_path=paths["spec"],
            research_path=paths["research"], dna_path=paths["dna"], scores_path=paths["scores"],
            message=f"{structure['name']}｜{dna.hook_type}｜{dna.shot_pattern}（综合分 {chosen.total:.3f}）",
        )

    def plan_batch(self, count: int, *, goal: str = "", day: str | None = None) -> list[PlannedJob]:
        """连续规划 N 条：候选按当日台账去重，所以 N 条之间天然互不雷同。"""
        day = day or self.today()
        out: list[PlannedJob] = []
        for i in range(max(0, int(count))):
            uid = self._new_uid(day, goal, i)
            out.append(self.plan_for(uid, index=i, goal=goal, day=day))
        return out

    # ── 幂等读取 ───────────────────────────────────────────────
    def load_planned(self, uid: str) -> PlannedJob | None:
        """已规划过（四份产物都在）→ 原样还原，不重复记使用、不重复打分。"""
        paths = self._paths(uid)
        if not paths["spec"].is_file() or not paths["dna"].is_file():
            return None
        try:
            spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
            dna_doc = json.loads(paths["dna"].read_text(encoding="utf-8"))
            scores_doc = (json.loads(paths["scores"].read_text(encoding="utf-8"))
                          if paths["scores"].is_file() else {})
            research_doc = (json.loads(paths["research"].read_text(encoding="utf-8"))
                            if paths["research"].is_file() else {})
        except (OSError, ValueError):
            return None
        dna = CreativeDNA.from_dict(dna_doc.get("dna") or {})
        return PlannedJob(
            uid=uid, index=0, day=str(dna_doc.get("day") or self.today()), dna=dna,
            structure={"id": dna_doc.get("structure", ""),
                       "name": dna_doc.get("structure_name", ""),
                       "_role_group": dna_doc.get("role_group", "")},
            hotspot=dict(spec.get("creative", {}).get("hotspot") or {}),
            research=dict(research_doc.get("brief") or {}),
            scores=dict(dna_doc.get("scores") or {}), shortlist=list(scores_doc.get("shortlist") or []),
            decision=dict((scores_doc.get("decision") if isinstance(scores_doc, dict) else {}) or {}),
            spec_path=paths["spec"], research_path=paths["research"], dna_path=paths["dna"],
            scores_path=paths["scores"],
            message=f"复用已规划方案：{dna_doc.get('structure_name', '')}",
        )

    # ── 落盘 ───────────────────────────────────────────────────
    def _paths(self, uid: str) -> dict[str, Path]:
        return {
            "spec": self.queue_dir / f"{uid}.json",
            "research": self.creative_dir / f"research_{uid}.json",
            "dna": self.creative_dir / f"dna_{uid}.json",
            "scores": self.creative_dir / f"scores_{uid}.json",
        }

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    def _new_uid(self, day: str, goal: str, index: int) -> str:
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "", goal or "")[:16] or "auto"
        stamp = self.now().strftime("%Y%m%d_%H%M%S")
        base = f"job_{day.replace('-', '')}_{slug}_{stamp}_{index + 1:02d}"
        uid, n = base, 1
        while (self.queue_dir / f"{uid}.json").exists() or self._known(uid):
            n += 1
            uid = f"{base}_{n}"
        return uid

    def _known(self, uid: str) -> bool:
        store = self.store
        if store is None:
            return False
        with suppress(Exception):
            return store.get_job(uid) is not None
        return False

    def _title(self, dna: CreativeDNA, structure: dict, hotspot) -> str:
        title = hotspot.title or "自动选题"
        return f"{title}｜{dna.hook_type}·{structure.get('name', '')}"[:60]

    # ── 当日台账（同日去重的事实来源，任务 11）─────────────────
    def _registry_path(self, day: str) -> Path:
        return self.creative_dir / f"day_{day}.json"

    def _load_registry(self, day: str) -> dict:
        path = self._registry_path(day)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("entries", [])
                    return data
            except (OSError, ValueError):
                pass
        return {"day": day, "entries": []}

    def _save_registry(self, day: str, registry: dict) -> None:
        registry["day"] = day
        self._write_json(self._registry_path(day), registry)

    def _append_registry(self, registry: dict, *, uid: str, dna: CreativeDNA,
                         structure: dict, day: str) -> dict:
        entries = list(registry.get("entries") or [])
        entries.append({
            "uid": uid, "day": day, "structure": structure.get("id", ""),
            "structure_name": structure.get("name", ""),
            "role_group": structure.get("_role_group", ""),
            "hook": dna.hook_type, "shot_pattern": dna.shot_pattern, "genre": dna.genre,
            "angle": dna.angle, "sales_point": dna.sales_point, "cast": dna.cast_pattern,
            "hotspot": dna.hotspot, "signature": list(dna.signature()),
        })
        registry["entries"] = entries
        return registry

    @staticmethod
    def _registry_lists(registry: dict) -> dict:
        entries = registry.get("entries") or []
        return {
            "hooks": [e.get("hook") for e in entries if e.get("hook")],
            "structures": [e.get("structure") for e in entries if e.get("structure")],
            "shot_patterns": [e.get("shot_pattern") for e in entries if e.get("shot_pattern")],
            "cast": [e.get("cast") for e in entries if e.get("cast")],
            "genres": [e.get("genre") for e in entries if e.get("genre")],
            "role_groups": [e.get("role_group") for e in entries if e.get("role_group")],
            "hotspots": [e.get("hotspot") for e in entries if e.get("hotspot")],
            "signatures": [tuple(e.get("signature") or []) for e in entries if e.get("signature")],
        }

    def _all_registries(self, limit: int = 60) -> list[dict]:
        if not self.creative_dir.is_dir():
            return []
        files = sorted(self.creative_dir.glob("day_*.json"), reverse=True)[:limit]
        out = []
        for path in files:
            with suppress(OSError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    out.append(data)
        return out

    def _registry_counts(self, field_name: str) -> dict:
        counts: dict = {}
        for registry in self._all_registries():
            for entry in registry.get("entries") or []:
                key = entry.get(field_name)
                if key:
                    counts[key] = counts.get(key, 0) + 1
        return counts

    # ── 记使用（继续沿用既有四池 + 创意去重库，任务 10）─────────
    def _record_usage(self, dna: CreativeDNA, structure: dict, uid: str) -> None:
        with suppress(Exception):
            genres_mod.record_genre(dna.genre, uid)
        with suppress(Exception):
            angles_mod.record_angle(dna.angle, uid)
        with suppress(Exception):
            products_mod.record_point(dna.sales_point, uid)
        group = structure.get("_role_group")
        if group:
            with suppress(Exception):
                cast_groups.record_group(group, uid)
        with suppress(Exception):
            ideas_mod.record_idea(structure.get("id", ""), structure.get("name", ""),
                                  dna.hotspot, {}, angle=dna.angle)


def plan_missing(*, store, daily_target: int, queue_dir=None, state_dir=None,
                 goal: str = "", count: int | None = None, **kwargs) -> list[PlannedJob]:
    """便捷入口：按 `daily_target - 今日已存在` 补齐并规划（编排器 `_plan_batch` 用）。"""
    planner = CreativePlanner(store=store, queue_dir=queue_dir, state_dir=state_dir, **kwargs)
    need = int(count) if count is not None else planner.needed(daily_target)
    if need <= 0:
        return []
    return planner.plan_batch(need, goal=goal)
