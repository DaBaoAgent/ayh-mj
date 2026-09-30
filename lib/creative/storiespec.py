"""StorySpec（Phase 5 必做任务 12）—— 明确的结构化故事规格，不是 H3 大 prompt。

计划明令："生成明确 StorySpec，不要直接让 LLM 输出最终 H3 大 prompt"。
所以 StorySpec 只描述**结构与事实**（骨架 / 卖点 / 角色 / 镜头节拍 / 热点依据），
H3 提示词的编译属于 Phase 7（PromptCompiler），此处 `prompt` 恒为空、`prompt_ready=False`。

`spec_payload()` 产出的 JSON 就是落进 `state/queue_15s/<uid>.json` 的队列 spec：
下游 `tools/make_15s.py` 需要的键（job_uid / prompt / ref_images / ref_audios …）一个不少，
另加 `creative` / `story_spec` 两块可追溯数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .dna import CreativeDNA

# 通用叙事节拍（按骨架镜数裁剪）
BEAT_LADDER = ("钩子", "冲突/悬念", "演示/转折", "收口卖点", "回味")

# Phase 9（任务 7）：每个叙事节拍的默认情绪/能量/标签 —— StorySpec 据此输出 mood_curve / beat_map，
# 由 Phase 9 的 AudioDirector 消费（不再靠文件大小或 random 选曲）。
BEAT_BASE: dict[str, dict] = {
    "钩子": {"mood": "upbeat", "energy": 0.85, "role": "hook", "tags": ["hook"]},
    "冲突/悬念": {"mood": "epic", "energy": 0.80, "role": "conflict", "tags": ["tension"]},
    "演示/转折": {"mood": "upbeat", "energy": 0.70, "role": "turn", "tags": ["turn", "demo"]},
    "收口卖点": {"mood": "upbeat", "energy": 0.60, "role": "brand", "tags": ["brand", "payoff"]},
    "回味": {"mood": "emotional", "energy": 0.35, "role": "close", "tags": ["warm"]},
}


def _genre_profile(genre: str) -> dict:
    """取片型的音频气质（与 AudioDirector 共用同一张表，避免两处各写一份）。"""
    try:
        from ..post.audio_director import GENRE_BGM_PROFILE

        return GENRE_BGM_PROFILE.get(genre) or {}
    except Exception:      # noqa: BLE001 - 音频层不可用时退回中性气质，不影响创意编译
        return {}


def _tone(beat: str, profile: dict) -> tuple[str, float]:
    """节拍情绪 × 片型气质 → (mood, energy)。

    片型 profile 的第一种气质是**主色**；钩子/悬念若片型有更"带劲"的第二气质就取它
    （开场要抓人）。能量按片型整体基调加减。这样同一套骨架在不同片型下得到明显不同的
    mood_curve，AudioDirector 才有得选（任务 7/10）。
    """
    base = BEAT_BASE.get(beat, BEAT_BASE["钩子"])
    moods = list(profile.get("mood") or [base["mood"]])
    mood = moods[0]
    if beat in ("钩子", "冲突/悬念") and len(moods) > 1 and moods[1] in ("epic", "upbeat", "comedic"):
        mood = moods[1]
    energy = base["energy"]
    tier = float(profile.get("energy", 0.5))
    if tier <= 0.35:
        energy = max(0.15, energy - 0.3)
    elif tier >= 0.8:
        energy = min(1.0, energy + 0.1)
    return mood, round(energy, 3)


def build_beat_map(structure: dict, dna: CreativeDNA) -> tuple[list[dict], list[dict]]:
    """按骨架镜数铺出叙事节拍表 → (beat_map, mood_curve)。

    beat_map 每镜带 role/tags/mood/energy（SFX 触发与留存分析用）；
    mood_curve 是同一张表的紧凑版（AudioDirector 选曲用）。
    """
    n = max(3, int(structure.get("shots") or 4))
    cast = [c for c in (dna.cast_pattern or "").split("+") if c.strip()] or ["@elder_male"]
    profile = _genre_profile(dna.genre)
    beat_map: list[dict] = []
    mood_curve: list[dict] = []
    for i in range(n):
        beat = BEAT_LADDER[i] if i < len(BEAT_LADDER) else BEAT_LADDER[-1]
        base = BEAT_BASE.get(beat, BEAT_BASE["钩子"])
        mood, energy = _tone(beat, profile)
        beat_map.append({
            "index": i + 1, "beat": beat, "role": base["role"], "mood": mood,
            "energy": energy, "tags": list(base["tags"]),
            "cast_ref": cast[i % len(cast)],
        })
        mood_curve.append({"index": i + 1, "beat": beat, "mood": mood, "energy": energy})
    return beat_map, mood_curve
DEFAULT_DURATION = 15
DEFAULT_RESOLUTION = "768p竖"
DEFAULT_WORKFLOW = "multi_image_15s"
FALLBACK_WORKFLOWS = ("multi_image_15s", "single_image_15s")
# Phase 7：spec 结构版本（写进 artifact，配合 compiler 版本保证可复现）
SPEC_VERSION = "storyspec/1.0"


@dataclass
class StorySpec:
    """一条视频的完整结构性规格（Phase 5 交付物）。"""

    uid: str
    structure_id: str
    structure_name: str
    dna: CreativeDNA
    hotspot: dict = field(default_factory=dict)
    research_refs: dict = field(default_factory=dict)
    title: str = ""
    duration: int = DEFAULT_DURATION
    resolution: str = DEFAULT_RESOLUTION
    workflow: str = DEFAULT_WORKFLOW
    fallback_workflows: list = field(default_factory=list)
    ref_images: list = field(default_factory=list)
    ref_audios: list = field(default_factory=list)
    shots: list = field(default_factory=list)
    mood_curve: list = field(default_factory=list)   # Phase 9：[{index,beat,mood,energy}]
    beat_map: list = field(default_factory=list)     # Phase 9：[{index,beat,role,mood,energy,tags}]
    lines: list = field(default_factory=list)   # Phase 7：[{shot, speaker, text}]，句数随骨架变
    prompt: str = ""
    prompt_ready: bool = False
    prompt_meta: dict = field(default_factory=dict)
    spec_version: str = SPEC_VERSION
    workflow_source: str = "static"    # 谁选的链：static / router
    first_last: bool = False
    text_only: bool = False
    rationale: dict = field(default_factory=dict)
    creative_paths: dict = field(default_factory=dict)
    claim_ids: list = field(default_factory=list)   # Phase 6：本条视频实际引用的产品 claim

    # ── 序列化 ─────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "structure_id": self.structure_id,
            "structure_name": self.structure_name, "dna": self.dna.to_dict(),
            "hotspot": dict(self.hotspot), "research_refs": dict(self.research_refs),
            "title": self.title, "duration": self.duration,
            "resolution": self.resolution, "workflow": self.workflow,
            "fallback_workflows": list(self.fallback_workflows),
            "ref_images": list(self.ref_images), "ref_audios": list(self.ref_audios),
            "shots": [dict(s) for s in self.shots],
            "mood_curve": [dict(x) for x in self.mood_curve],
            "beat_map": [dict(x) for x in self.beat_map],
            "prompt": self.prompt,
            "prompt_ready": self.prompt_ready,
            "lines": [dict(x) if isinstance(x, dict) else x for x in self.lines],
            "prompt_meta": dict(self.prompt_meta), "spec_version": self.spec_version,
            "workflow_source": self.workflow_source,
            "first_last": self.first_last, "text_only": self.text_only,
            "claim_ids": list(self.claim_ids),
        }

    def to_spec_json(self) -> dict:
        """落盘成队列 spec（下游 make_15s / 编排器读这份）。"""
        payload = {
            "job_uid": self.uid,
            "title": self.title,
            "goal": self.dna.hotspot,
            "duration": self.duration,
            "resolution": self.resolution,
            "workflow": self.workflow,
            "fallback_workflows": list(self.fallback_workflows),
            "prompt": self.prompt,
            "prompt_ready": self.prompt_ready,
            "plan_only": not self.prompt_ready,
            "prompt_meta": dict(self.prompt_meta),
            "spec_version": self.spec_version,
            "workflow_source": self.workflow_source,
            "first_last": self.first_last,
            "text_only": self.text_only,
            "claim_ids": list(self.claim_ids),
            "ref_images": list(self.ref_images),
            "ref_audios": list(self.ref_audios),
            "creative": {
                "structure": self.structure_id,
                "structure_name": self.structure_name,
                "dna": self.dna.to_dict(),
                "hotspot": dict(self.hotspot),
                "rationale": dict(self.rationale),
                "artifacts": dict(self.creative_paths),
                "claim_ids": list(self.claim_ids),
            },
            "story_spec": self.to_dict(),
        }
        return payload


def build_shots(structure: dict, dna: CreativeDNA) -> list[dict]:
    """按骨架镜数铺出镜头节拍表（结构信息，不含成句台词/提示词）。"""
    n = max(3, int(structure.get("shots") or 4))
    cast = [c for c in (dna.cast_pattern or "").split("+") if c.strip()] or ["@elder_male"]
    shots: list[dict] = []
    for i in range(n):
        beat = BEAT_LADDER[i] if i < len(BEAT_LADDER) else BEAT_LADDER[-1]
        shots.append({
            "index": i + 1,
            "beat": beat,
            "camera_language": structure.get("camera_language", ""),
            "cast_ref": cast[i % len(cast)],
            "visual_motif": dna.visual_motif if beat in ("冲突/悬念", "演示/转折") else "",
            "product_role": dna.product_role,
            "dialogue_mode": dna.dialogue_mode,
            "note": structure.get("directions", "") if i == 0 else "",
        })
    return shots


def build_story_spec(*, uid: str, structure: dict, dna: CreativeDNA, hotspot: dict,
                     research_refs: dict, rationale: dict, title: str,
                     creative_paths: dict | None = None,
                     claim_ids: list | None = None,
                     duration: int = DEFAULT_DURATION,
                     resolution: str = DEFAULT_RESOLUTION,
                     workflow: str = DEFAULT_WORKFLOW,
                     lines: list | None = None,
                     first_last: bool = False,
                     text_only: bool = False) -> StorySpec:
    """装配 StorySpec（唯一定稿入口，Planner 与 CLI 共用）。"""
    beat_map, mood_curve = build_beat_map(structure, dna)
    return StorySpec(
        uid=uid, structure_id=structure["id"], structure_name=structure["name"],
        dna=dna, hotspot=dict(hotspot or {}), research_refs=dict(research_refs or {}),
        title=title, duration=duration, resolution=resolution, workflow=workflow,
        fallback_workflows=[w for w in FALLBACK_WORKFLOWS if w != workflow],
        shots=build_shots(structure, dna),
        mood_curve=mood_curve, beat_map=beat_map,
        lines=[dict(x) if isinstance(x, dict) else x for x in (lines or [])],
        rationale=dict(rationale or {}), first_last=bool(first_last),
        text_only=bool(text_only),
        creative_paths=dict(creative_paths or {}),
        claim_ids=list(claim_ids or []),
    )


def summarize_research(brief: dict) -> dict:
    """研究全文另存 artifact；spec 里只放可追溯的摘要指针，避免 spec 变胖。"""
    if not brief:
        return {}
    hs = brief.get("hotspot") or {}
    return {
        "hotspot_title": hs.get("title", ""),
        "hotspot_source": hs.get("platform") or hs.get("source", ""),
        "hotspot_url": hs.get("url", ""),
        "related_topics": [t.get("title", "") for t in brief.get("related_topics") or []],
        "viral_example_count": len(brief.get("viral_examples") or []),
        "benchmark_pattern_count": len(brief.get("benchmark_patterns") or []),
        "short_drama_rule_chars": len(brief.get("short_drama_rules") or ""),
        "inventory": brief.get("inventory") or {},
    }
