"""Phase 7 测试共享工具 —— 把 10 个结构骨架变成可编译/可路由的 StorySpec。"""
from __future__ import annotations

from lib.creative.storiespec import BEAT_LADDER, DEFAULT_RESOLUTION, SPEC_VERSION
from lib.products import ROOT as _ROOT

# 参考图（真实存在的产品图）—— 路由需要 >=1 张参考图才能选到 15s 多图型号
REF_IMAGES: list[str] = [str(_ROOT / "assets" / "products" / "主图1.jpg"),
                            str(_ROOT / "assets" / "products" / "主图2.jpg")]

# 骨架 → 片型（用于 CINEDANCE 动态启用断言）
STRUCTURE_GENRE: dict[str, str] = {
    "S_duo_conflict": "G1",
    "S_solo_vlog": "G7",
    "S_street_interview": "G6",
    "S_suspense_reveal": "G9",
    "S_magic_loop": "G3",
    "S_product_test": "G10",
    "S_pov_first": "G4",
    "S_silent_slapstick": "G8",
    "S_emotional_story": "G5",
    "S_comment_reply": "G2",
}

# 每种台词模式的示例台词（无数字/无单位，避免误触 Phase 6 合规门）
MODE_LINES: dict[str, list[str]] = {
    "双人对白": ["这个真的能行吗", "你自己看，单手就拎起来了", "真有这么轻", "对，单手就够"],
    "单人口播": ["今天当着大家的面做个小测试", "先看这个折叠动作", "再看它在窄道里的表现"],
    "街访问答": ["您猜这个有多重", "看着挺沉，其实单手就能提", "真没想到这么轻"],
    "画外音旁白": ["早上出门，它就在门口等着", "路上遇到台阶，推着就过去了",
                   "晚上回家，收起来不占地方"],
    "字幕驱动": ["画面出现一个神秘包装", "拆开后露出整车"],
    "无对白": [],
}


def lines_for(dialogue_mode: str, slots: list[str]) -> list[dict]:
    """按台词模式造台词（双人对白左右交替，其余都给首位说话人）。"""
    texts = MODE_LINES.get(dialogue_mode, [])
    if not texts:
        return []
    out: list[dict] = []
    two = dialogue_mode == "双人对白" and len(slots) >= 2
    n = max(1, len(texts))
    for i, text in enumerate(texts):
        shot = 1 + int(i * 4 / n)
        speaker = slots[0] if (not two or i % 2 == 0) else slots[1 % len(slots)]
        out.append({"shot": min(4, shot), "speaker": speaker, "text": text})
    return out


def dna_for(structure: dict) -> dict:
    """由骨架 + 受控词表造一份最小的、能过 compile 的 CreativeDNA dict。"""
    return {
        "audience": "子女代购决策者",
        "goal": "让人记住一个卖点",
        "hotspot": structure["name"],
        "genre": STRUCTURE_GENRE.get(structure["id"], "G1"),
        "angle": structure["narrative_arc"],
        "sales_point": "单手提起",
        "hook_type": structure["hook_types"][0],
        "narrative_arc": structure["narrative_arc"],
        "shot_pattern": structure["shot_pattern"],
        "cast_pattern": structure["cast_pattern"],
        "product_role": structure["product_role"],
        "conflict_type": structure["conflict_type"],
        "visual_motif": structure["visual_motif"],
        "camera_language": structure["camera_language"],
        "dialogue_mode": structure["dialogue_mode"],
        "audio_mode": structure["audio_mode"],
        "payoff": "把卖点收在一个干净利落的动作上",
        "ending": "画面停在产品与人物同框的瞬间",
        "CTA": "点开头像看看同款",
        "risk_flags": [],
    }


def shots_for(structure: dict) -> list[dict]:
    n = int(structure["shots"])
    slots = [s for s in structure["cast_pattern"].split("+") if s.strip()]
    out: list[dict] = []
    for i in range(n):
        out.append({
            "index": i + 1,
            "beat": BEAT_LADDER[min(i, len(BEAT_LADDER) - 1)],
            "camera_language": structure["camera_language"],
            "cast_ref": slots[i % len(slots)],
            "visual_motif": structure["visual_motif"],
            "product_role": structure["product_role"],
            "dialogue_mode": structure["dialogue_mode"],
            "note": "",
        })
    return out


def spec_for(structure: dict, *, uid: str = "", duration: int = 15,
             lines=None, claim_ids=None) -> dict:
    """骨架 → 与 Planner 落盘同口径的 spec dict（供编译器/路由/编排器吃）。"""
    dna = dna_for(structure)
    slots = [s for s in dna["cast_pattern"].split("+") if s.strip()]
    uid = uid or f"P7_{structure['id']}"
    story_lines = lines if lines is not None else lines_for(dna["dialogue_mode"], slots)
    story = {
        "uid": uid, "structure_id": structure["id"], "structure_name": structure["name"],
        "dna": dna, "hotspot": {"title": structure["name"]},
        "title": f"骨架演示 {structure['name']}", "duration": duration,
        "resolution": DEFAULT_RESOLUTION, "workflow": "", "fallback_workflows": [],
        "ref_images": list(REF_IMAGES), "ref_audios": [], "shots": shots_for(structure),
        "lines": story_lines, "prompt": "", "prompt_ready": False,
        "prompt_meta": {}, "spec_version": SPEC_VERSION, "workflow_source": "static",
        "first_last": False, "text_only": False, "claim_ids": list(claim_ids or []),
    }
    return {
        "job_uid": uid,
        "title": f"骨架演示 {structure['name']}",
        "duration": duration,
        "resolution": DEFAULT_RESOLUTION,
        "workflow": "",
        "prompt": "",
        "prompt_ready": False,
        "plan_only": True,
        "prompt_meta": {},
        "spec_version": SPEC_VERSION,
        "workflow_source": "static",
        "ref_images": list(REF_IMAGES),
        "claim_ids": list(claim_ids or []),
        "creative": {"structure": structure["id"], "structure_name": structure["name"],
                     "dna": dna, "claim_ids": list(claim_ids or [])},
        "story_spec": story,
    }
