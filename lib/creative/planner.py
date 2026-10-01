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
import random
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import STATE_DIR
from .. import angles as angles_mod
from .. import claims as claims_mod
from .. import genres as genres_mod
from .. import ideas as ideas_mod
from .. import products as products_mod
from ..creative_research import build_research_brief
from . import cast_groups
from .compiler import PromptBudgetExceeded, compile_spec, gate_text, lines_from_file
from .director import CreativeDirector
from .dna import AUDIENCES, CLAIM_BLOCKED_FLAG, CLAIM_RISK_FLAG, GOALS, VISUAL_MOTIFS, CreativeDNA
from .hotspot import normalize_hotspot
from .scoring import NUMERIC_CLAIM_POINTS, STRUCTURE_AUDIENCES
from .storiespec import SPEC_VERSION, build_story_spec, summarize_research
from .structures import (
    STORY_STRUCTURES,
    cast_pattern_for_topic,
    compatible_genres,
    structure_allowed_for_topic,
)
from .workflow import route_for_spec
from .writer import StoryWriter, StoryWritingError, needs_text, validate_lines

ROOT = Path(__file__).resolve().parent.parent.parent
DAY_FMT = "%Y-%m-%d"
CANDIDATE_MIN, CANDIDATE_MAX = 10, 20
MAX_ATTEMPTS = 800
EVERGREEN_RISK = "热点为常青素材，时效性弱"
SILENT_RISK = "无对白需字幕/音效兜底"

# Phase 7：产品单元素材（与 tools/make_15s.py 的 REFS_TAIL 同口径）
PRODUCT_REFS: tuple[str, ...] = ("折叠-无阴影.png", "正侧-3-无阴影.png", "45度-加水杯-无阴影.png")
MAX_REF_IMAGES = 9          # H3 多图参考上限（实际按工作流能力再校验）

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
    claims_path: Path | None = None
    gate_path: Path | None = None
    message: str = ""

    def artifacts(self) -> list[dict]:
        """登记进 JobStore 的 artifact 清单（顺序即展示顺序）。"""
        out = [{"type": "spec", "path": str(self.spec_path)}] if self.spec_path else []
        for type_, path in (("research", self.research_path),
                            ("creative_dna", self.dna_path),
                            ("creative_scores", self.scores_path),
                            ("claims", self.claims_path),
                            ("dialogue_check", self.gate_path)):
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
            "claims_path": str(self.claims_path or ""),
            "gate_path": str(self.gate_path or ""),
            "message": self.message,
        }


class CreativePlanner:
    """自主选题 / 创意规划器（唯一实现）。"""

    def __init__(self, *, queue_dir: Path | str | None = None,
                 state_dir: Path | str | None = None, store=None,
                 director: CreativeDirector | None = None,
                 writer: StoryWriter | None = None,
                 candidate_count: int = 16, seed: str = "",
                 now: datetime | None = None,
                 learn: bool | None = None, explore_ratio: float | None = None,
                 rng: random.Random | None = None) -> None:
        self.state_dir = Path(state_dir) if state_dir else Path(STATE_DIR)
        self.queue_dir = Path(queue_dir) if queue_dir else self.state_dir / "queue_15s"
        self.creative_dir = self.state_dir / "creative"
        self.store = store
        self.director = director or CreativeDirector()
        self.writer = writer or StoryWriter()
        self.candidate_count = max(CANDIDATE_MIN, min(CANDIDATE_MAX, int(candidate_count)))
        self.seed = str(seed or "")
        self._now = now
        # Phase 11：学习层（None = 跟随 settings.learn.enabled）
        self._learn = learn
        self._explore_ratio = explore_ratio
        self._rng = rng
        self._model = None
        self._model_loaded = False

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
        excluded = {"FAILED", "CANCELLED", "BLOCKED", "PAUSED", "VOID"}
        count = 0
        for job in store.list_jobs(limit=500):
            created = str(job.get("created_at") or "")[:10]
            uid = str(job.get("uid") or "")
            if (created == day and not re.search(r"_shot\d+$", uid)
                    and str(job.get("status") or "").upper() not in excluded):
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
            if not structure_allowed_for_topic(structure["id"], str(trend.get("title") or "")):
                continue
            allowed_genres = set(compatible_genres(structure["id"]))
            genre_pool = [g for g in genres_ordered if not allowed_genres or g["id"] in allowed_genres]
            if not genre_pool:
                continue
            genre = genre_pool[(layer + i) % len(genre_pool)]
            angle = angles_ordered[(layer * 3 + i) % len(angles_ordered)]
            point_pool = products_mod.compatible_points(
                topic=str(trend.get("title") or ""), structure_id=structure["id"],
                genre_id=genre["id"], visual_motif=str(structure.get("visual_motif") or ""))
            if not point_pool:
                continue
            # 只在语义适配池内做轮换；高适配优先，同分再由使用次数决定。
            point = point_pool[(layer + i) % min(len(point_pool), 5)]
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
        usable = bool(point.get("usable"))
        if point["id"] in NUMERIC_CLAIM_POINTS:
            risks.append(CLAIM_RISK_FLAG)
        if not usable:                       # 口径待核验/禁止使用：文案里不许出现该口径
            risks.append(CLAIM_BLOCKED_FLAG)
        if trend.get("source_type") != "live":
            risks.append(EVERGREEN_RISK)
        if structure.get("dialogue_mode") == "无对白":
            risks.append(SILENT_RISK)
        return CreativeDNA(
            audience=audience, goal=GOALS[index % len(GOALS)], hotspot=str(trend.get("title") or ""),
            genre=genre["id"], angle=angle["id"], sales_point=point["id"], hook_type=hook,
            narrative_arc=structure["narrative_arc"], shot_pattern=structure["shot_pattern"],
            cast_pattern=cast_pattern_for_topic(structure["id"], str(trend.get("title") or ""),
                                                structure["cast_pattern"]),
            product_role=structure["product_role"],
            conflict_type=structure["conflict_type"], visual_motif=motif,
            camera_language=structure["camera_language"], dialogue_mode=structure["dialogue_mode"],
            audio_mode=structure["audio_mode"],
            payoff=(f"{point['hook']}｜{structure['name']}把它收在{point['name']}上" if usable
                    else f"{structure['name']}用它把故事收住（卖点口径待核验，暂不出参数）"),
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

    # ── 学习层（Phase 11）：历史表现先验 ───────────────────────
    def learn_config(self) -> dict:
        """读 settings.learn（配置不可用时退回内置默认值，绝不让规划挂掉）。"""
        defaults = {"enabled": True, "exploit_ratio": 0.8, "window_days": 30,
                    "history_weight": 0.25, "prior_n": 5.0, "min_medium": 8, "min_high": 30}
        try:
            from ..settings import get_settings
            cfg = get_settings().learn
        except Exception:                          # noqa: BLE001 - 缺 yaml/配置也要能规划
            return defaults
        return {"enabled": bool(cfg.enabled), "exploit_ratio": float(cfg.exploit_ratio),
                "window_days": int(cfg.window_days), "history_weight": float(cfg.history_weight),
                "prior_n": float(cfg.prior_n), "min_medium": int(cfg.min_samples_medium),
                "min_high": int(cfg.min_samples_high)}

    def performance_model(self):
        """读本地表现快照建模型（只读、可空；失败一律退回 None）。"""
        if self._model_loaded:
            return self._model
        self._model_loaded = True
        cfg = self.learn_config()
        if self._learn is False or (self._learn is None and not cfg["enabled"]):
            return None
        try:
            from s7_learn import pipeline as learn_pipeline
            store = self.store
            if store is None:
                from ..jobstore import store as default_store
                store = default_store
            model = learn_pipeline.history_for_planner(
                self.state_dir.parent, store, window_days=cfg["window_days"],
                prior_n=cfg["prior_n"], min_medium=cfg["min_medium"],
                min_high=cfg["min_high"])
            # 一条可用样本都没有 → 当作"没有历史"，而不是交出一个空模型让人误会
            self._model = model if (model is not None and model.n_samples > 0) else None
        except Exception:                          # noqa: BLE001 - 学习不可用不能阻断生产
            self._model = None
        return self._model

    # ── 规划一个 job ───────────────────────────────────────────
    def plan_for(self, uid: str, *, index: int = 0, goal: str = "", day: str | None = None,
                 force: bool = False, avoid_prescreen: bool = False,
                 preferred_structures: tuple[str, ...] = ()) -> PlannedJob:
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
        # Phase 11：把历史表现当先验注入候选评分（无历史时行为与 Phase 5 完全一致）
        from s7_learn import scorer as learn_scorer
        cfg = self.learn_config()
        model = self.performance_model()
        hook = learn_scorer.history_hook(model)
        context = {"used_counts": self.used_counts(), "day_registry": self._registry_lists(registry),
                   "trend": hotspot.to_dict(), "claim_points": sorted(NUMERIC_CLAIM_POINTS),
                   "history_weight": cfg["history_weight"]}
        if hook is not None:
            context["history"] = hook
        ranked = self.director.rank(cands, context=context)
        if preferred_structures:
            preferred = [candidate for candidate in ranked
                         if candidate.structure.get("id") in set(preferred_structures)]
            if preferred:
                ranked = preferred
        if avoid_prescreen:
            from .prescreen import needs_prescreen
            ranked = [candidate for candidate in ranked
                      if candidate.dna.dialogue_mode == "无对白"
                      and not needs_prescreen({"creative": {
                          "dna": candidate.dna.to_dict(),
                          "structure": candidate.structure.get("id", "")}})]
            if not ranked:
                raise PlannerError("本轮没有可直接制作的无对白方案；候选需预筛或补充文案，请在任务台处理")
        ratio = (self._explore_ratio if self._explore_ratio is not None
                 else cfg["exploit_ratio"])
        selection = learn_scorer.select(ranked, model, ratio=ratio, rng=self._rng, hook=hook)
        decision = self.director.decide(ranked, selection=selection)
        chosen = decision["chosen"]
        if chosen is None:
            raise PlannerError("候选评分没有产生终选方案")
        dna: CreativeDNA = chosen.dna
        structure = chosen.structure

        claim_ids = products_mod.claim_ids_for(dna.sales_point)
        claim_facts = _claim_artifact(claim_ids)
        # 9/26 稳定链的关键顺序：先把完整文案写好并通过字数/句数合同，再造 spec/prompt。
        # Phase 5 初版把这一层漏掉，只“尝试读取已有 lines 文件”，导致自主任务可带空对白进入编译。
        try:
            draft = self.writer.write(hotspot=hotspot.to_dict(), dna=dna,
                                      structure=structure, research=brief)
        except StoryWritingError as exc:
            raise PlannerError(f"文案阶段未通过，禁止进入 AutoDL：{exc}") from exc
        # CreativeDNA.goal 是受控枚举（用于统计/学习），Writer 的自然语言故事目标不能覆盖它。
        dna.payoff = draft.payoff or dna.payoff
        dna.ending = draft.ending or dna.ending
        dna.CTA = draft.cta or dna.CTA
        title = draft.title or self._title(dna, structure, hotspot)
        rationale = {
            "rule": decision["rule"], "note": decision["note"],
            "totals": {s.to_dict()["structure"]: s.total for s in ranked[:5]},
            "reasons": dict(decision.get("reasons") or {}),
            "candidate_count": len(ranked),
            "claim_ids": claim_ids,
            "history": {
                "model": ({"n_samples": model.n_samples, "confidence": model.confidence(),
                           "global_mean": model.global_mean, "window_days": model.window_days,
                           "window": dict(model.window), "low_confidence": model.low_confidence(),
                           "platforms": list(model.platforms)}
                          if model is not None else None),
                "selection": {k: v for k, v in selection.items() if k != "chosen"},
            },
        }
        rationale["writer"] = {"source": draft.source, "line_count": len(draft.lines),
                                "story_goal": draft.goal}
        spec = build_story_spec(uid=uid, structure=structure, dna=dna, hotspot=hotspot.to_dict(),
                                research_refs=summarize_research(brief), rationale=rationale,
                                title=title, claim_ids=claim_ids, lines=draft.lines)
        for shot, note in zip(spec.shots, draft.shot_notes, strict=False):
            if note:
                shot["note"] = note
        self._persist_lines(spec)
        # Phase 7：① 补参考素材（角色槽位 → 定妆图/音色 + 产品单元素材）
        #          ② 编译 H3 提示词（PromptCompiler，唯一实现）
        #          ③ 能力感知路由（不再人工固定空 fallback，任务 8/9）
        self._attach_lines(spec)
        self._attach_assets(spec)
        compile_meta = self._compile_prompt(spec)
        route_meta = self._route_prompt(spec)
        rationale["compile"] = compile_meta
        rationale["route"] = route_meta
        paths = self._paths(uid)
        self._write_json(paths["research"], {"uid": uid, "day": day, "brief": brief})
        self._write_json(paths["dna"], {"uid": uid, "day": day, "structure": structure["id"],
                                        "structure_name": structure["name"],
                                        "role_group": structure.get("_role_group", ""),
                                        "dna": dna.to_dict(), "hotspot": hotspot.to_dict(),
                                        "scores": dict(chosen.scores), "rationale": rationale,
                                        "claim_ids": claim_ids})
        self._write_json(paths["claims"], claim_facts)
        # 静态对白门禁 payload（duration="N" 一定带上，R10/R28 语速预算才是真开着的）
        paths["gate"].parent.mkdir(parents=True, exist_ok=True)
        paths["gate"].write_text(
            gate_text(spec.prompt, duration=spec.duration, resolution=spec.resolution),
            encoding="utf-8")
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
            claims_path=paths["claims"], gate_path=paths["gate"],
            message=(f"{structure['name']}｜{dna.hook_type}｜{dna.shot_pattern}"
                     f"（综合分 {chosen.total:.3f}；{spec.duration}s/{len(spec.shots)} 镜/"
                     f"{len(spec.lines)} 句；{spec.workflow}）"),
        )

    def plan_batch(self, count: int, *, goal: str = "", day: str | None = None,
                   avoid_prescreen: bool = False) -> list[PlannedJob]:
        """连续规划 N 条：语义适配优先，同时给大批次保留关键片型覆盖。"""
        day = day or self.today()
        total = max(0, int(count))
        out: list[PlannedJob] = []
        # 只对 4 条以上批次启用软覆盖；单条任务永远只按语义/表现评分选最合适方案。
        coverage_groups: list[tuple[str, ...]] = []
        if total >= 4 and not avoid_prescreen:
            coverage_groups = [
                ("S_solo_vlog",),
                ("S_suspense_reveal",),
                ("S_product_test",),
                ("S_magic_loop", "S_pov_first", "S_silent_slapstick"),
            ]
        covered: set[str] = set()
        for i in range(total):
            uid = self._new_uid(day, goal, i)
            preferred: tuple[str, ...] = ()
            for group in coverage_groups:
                if not (set(group) & covered):
                    preferred = group
                    break
            planned = self.plan_for(uid, index=i, goal=goal, day=day,
                                    avoid_prescreen=avoid_prescreen,
                                    preferred_structures=preferred)
            out.append(planned)
            covered.add(str(planned.structure.get("id") or ""))
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
            scores_path=paths["scores"], claims_path=paths["claims"], gate_path=paths["gate"],
            message=f"复用已规划方案：{dna_doc.get('structure_name', '')}",
        )

    # ── 落盘 ───────────────────────────────────────────────────
    def _paths(self, uid: str) -> dict[str, Path]:
        return {
            "spec": self.queue_dir / f"{uid}.json",
            "research": self.creative_dir / f"research_{uid}.json",
            "dna": self.creative_dir / f"dna_{uid}.json",
            "scores": self.creative_dir / f"scores_{uid}.json",
            "claims": self.creative_dir / f"claims_{uid}.json",
            "gate": self.creative_dir / f"gate_{uid}.txt",
        }

    # ── Phase 7：素材 / 编译 / 路由 ────────────────────────────
    def _persist_lines(self, spec) -> None:
        """同步旧版 `docs/onetake_lines_<uid>.txt`，保留 9/26 工具链兼容性。

        docs 跟随 state 的父目录：生产 `ROOT/state -> ROOT/docs`；pytest 的临时
        `tmp/state -> tmp/docs`。这样测试不会再向真实仓库写一地兼容台词文件。
        """
        if not spec.lines:
            return
        docs_dir = self.state_dir.parent / "docs"
        path = docs_dir / f"onetake_lines_{spec.uid}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(str(row.get("text") or "") for row in spec.lines) + "\n",
                        encoding="utf-8")

    def _attach_lines(self, spec) -> None:
        """装入兼容旧稿并执行**付费前硬合同**；需要文字的片绝不允许空 lines。"""
        if not spec.lines:
            slots = [s for s in str(spec.dna.cast_pattern or "").split("+") if s.strip()]
            spec.lines = lines_from_file(spec.uid, max(1, len(spec.shots)),
                                         spec.dna.dialogue_mode, slots)
        problems = validate_lines(spec.lines, dna=spec.dna,
                                  structure={"id": spec.structure_id, "shots": len(spec.shots)})
        if needs_text(spec.dna.dialogue_mode) and problems:
            raise PlannerError("对白合同未通过，禁止编译/付费生成：" + "；".join(problems))

    def _attach_assets(self, spec) -> None:
        """把 StorySpec 的 `@槽位` 解析成真实参考素材（图 + 音色）。

        与 tools/make_15s.py 的人工 spec 同口径：人物定妆图在前、产品单元素材在后。
        解析不了的槽位**只记警告不抛错** —— 宁可让 preflight 用 CAPABILITY/ASSET 门拦，
        也不要在规划期把整条任务炸掉（规划本身不花钱，可反复重试）。
        """
        from .. import cast as cast_mod

        warnings: list[str] = []
        images: list[str] = []
        audios: list[str] = []
        picked: dict[str, str] = {}

        def _add(paths, bucket: list[str]) -> None:
            for raw in paths:
                p = Path(raw)
                if p.is_file() and str(p) not in bucket:
                    bucket.append(str(p))

        # Reference image N and reference audio N must describe the same cast slot.
        # Shot order and first spoken-line order are not reliable cast order.
        slots = [s.strip() for s in str(spec.dna.cast_pattern or "").split("+") if s.strip()]
        image_bindings: dict[str, str] = {}
        voice_bindings: dict[str, str] = {}
        for ref in slots:
            role = ref
            try:
                if ref.startswith("@"):
                    role = picked.setdefault(ref, cast_mod._pick_from_slot(ref, spec.uid))
                refs = cast_mod.resolve_refs([role])
                _add(refs, images)
                if refs:
                    image_bindings[ref] = str(refs[0])
                voice = cast_mod.resolve_voice(role)
                if voice and Path(voice).is_file():
                    audios.append(str(voice))
                    voice_bindings[ref] = str(voice)
                else:
                    warnings.append(f"voice {ref}: missing for {role}")
            except Exception as exc:      # noqa: BLE001 —— 缺图不该炸规划
                warnings.append(f"{ref}: {type(exc).__name__}: {exc}")

        for shot in spec.shots:
            ref = str((shot or {}).get("cast_ref") or "")
            if not ref or ref in slots:
                continue
            try:
                role = picked.setdefault(ref, cast_mod._pick_from_slot(ref, spec.uid)) if ref.startswith("@") else ref
                _add(cast_mod.resolve_refs([role]), images)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{ref}: {type(exc).__name__}: {exc}")

        # 产品单元素材（有就带上：产品保真的唯一依据是同一条产品参考图）
        product_dir = ROOT / "assets" / "products"
        _add([product_dir / name for name in PRODUCT_REFS
              if (product_dir / name).is_file()], images)

        spec.ref_images = images[:MAX_REF_IMAGES]
        spec.ref_audios = audios
        if warnings:
            spec.prompt_meta.setdefault("asset_warnings", warnings)
        spec.prompt_meta["assets"] = {"ref_images": len(spec.ref_images),
                                      "ref_audios": len(spec.ref_audios),
                                      "cast_slots": slots,
                                      "image_bindings": image_bindings,
                                      "voice_bindings": voice_bindings}

    def _compile_prompt(self, spec) -> dict:
        """PromptCompiler：唯一编译入口。失败**不抛**，改标 plan_only 让 preflight 拦。"""
        keep = dict(spec.prompt_meta)
        spec.spec_version = SPEC_VERSION
        try:
            compiled = compile_spec(spec)
        except PromptBudgetExceeded as exc:
            spec.prompt, spec.prompt_ready = "", False
            spec.prompt_meta = {**keep, "compiler_version": "prompt-compiler/1.0",
                                "error": "PROMPT_BUDGET_EXCEEDED", "detail": str(exc)}
            return {"ok": False, "error": "PROMPT_BUDGET_EXCEEDED", "detail": str(exc)}
        spec.prompt = compiled.prompt
        spec.prompt_ready = True
        spec.prompt_meta = {**keep, **compiled.to_dict(), "chars": len(compiled.prompt)}
        return {"ok": True, **compiled.to_dict()}

    def _route_prompt(self, spec) -> dict:
        """能力感知路由：一次算清首选 + 兼容 fallback（任务 8/9）。"""
        from .prescreen import risk_of

        risk = risk_of(spec)
        try:
            plan = route_for_spec(spec, risk=risk["level"])
        except Exception as exc:      # noqa: BLE001 —— 路由失败不炸规划，留给 preflight
            spec.prompt_meta["route_error"] = f"{type(exc).__name__}: {exc}"
            return {"ok": False, "error": type(exc).__name__, "detail": str(exc),
                    "risk": risk}
        spec.workflow = plan.workflow
        spec.fallback_workflows = list(plan.fallbacks)
        spec.workflow_source = "router"
        spec.resolution = plan.resolution
        spec.prompt_meta["route"] = plan.to_dict()
        spec.prompt_meta["risk"] = risk
        return {"ok": True, **plan.to_dict(), "risk": risk}

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


def _claim_artifact(claim_ids: list[str], channel: str = "script") -> dict:
    """本条视频实际引用的 claim 快照（Phase 6 任务 7：发布 artifact 的 claim_id 列表）。"""
    try:
        reg = claims_mod.load()
    except Exception as exc:
        return {"claim_ids": list(claim_ids), "error": f"{type(exc).__name__}: {exc}",
                "claims": [], "usable": {}, "gate": {"ok": False}}
    rows, usable = [], {}
    for cid in claim_ids:
        claim = reg.get(cid)
        usable[cid] = bool(claim is not None and claim.usable(channel))
        rows.append(claim.to_dict() if claim else {"claim_id": cid, "status": "missing"})
    return {"claim_ids": list(claim_ids), "channel": channel, "usable": usable,
            "claims": rows,
            "status_counts": reg.status_counts(),
            "digest": reg.digest()[:16],
            "gate": {"ok": all(usable.values()) if usable else True}}
