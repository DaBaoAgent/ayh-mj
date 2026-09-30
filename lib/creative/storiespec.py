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
DEFAULT_DURATION = 15
DEFAULT_RESOLUTION = "768p竖"
DEFAULT_WORKFLOW = "multi_image_15s"
FALLBACK_WORKFLOWS = ("multi_image_15s", "single_image_15s")


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
    prompt: str = ""
    prompt_ready: bool = False
    rationale: dict = field(default_factory=dict)
    creative_paths: dict = field(default_factory=dict)

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
            "shots": [dict(s) for s in self.shots], "prompt": self.prompt,
            "prompt_ready": self.prompt_ready,
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
            "ref_images": list(self.ref_images),
            "ref_audios": list(self.ref_audios),
            "creative": {
                "structure": self.structure_id,
                "structure_name": self.structure_name,
                "dna": self.dna.to_dict(),
                "hotspot": dict(self.hotspot),
                "rationale": dict(self.rationale),
                "artifacts": dict(self.creative_paths),
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
                     duration: int = DEFAULT_DURATION,
                     resolution: str = DEFAULT_RESOLUTION,
                     workflow: str = DEFAULT_WORKFLOW) -> StorySpec:
    """装配 StorySpec（唯一定稿入口，Planner 与 CLI 共用）。"""
    return StorySpec(
        uid=uid, structure_id=structure["id"], structure_name=structure["name"],
        dna=dna, hotspot=dict(hotspot or {}), research_refs=dict(research_refs or {}),
        title=title, duration=duration, resolution=resolution, workflow=workflow,
        fallback_workflows=[w for w in FALLBACK_WORKFLOWS if w != workflow],
        shots=build_shots(structure, dna), rationale=dict(rationale or {}),
        creative_paths=dict(creative_paths or {}),
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
