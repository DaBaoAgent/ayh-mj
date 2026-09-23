"""创意去重库 — 记录用过的创意点（热点/梗/角度），防"一个点用了又用"

机制：
  1. 每条成片的分镜确定后，record_idea() 记录其创意要素
  2. 生成新文案前 ideas_block() 输出"已用过清单"，注入 LLM 提示词强制避开
  3. 热点选择也跳过已用（_latest_hotspot 联动 used_hotspots()）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDEAS_STATE = ROOT / "state" / "used_ideas.json"


def load_ideas() -> list[dict]:
    if IDEAS_STATE.exists():
        try:
            return json.loads(IDEAS_STATE.read_text(encoding="utf-8")).get("ideas", [])
        except Exception:
            return []
    return []


def used_hotspots() -> set[str]:
    """已使用过的热点标题集合"""
    return {i.get("hotspot", "") for i in load_ideas() if i.get("hotspot")}


def ideas_block(limit: int = 12) -> str:
    """给 LLM 的"禁止重复"提示块"""
    ideas = load_ideas()[-limit:]
    if not ideas:
        return ""
    lines = ["【已用过的创意点（本次必须完全避开，一个点用过就不再使用）】"]
    for i, idea in enumerate(ideas, 1):
        bits = [f"{idea.get('template', '')} {idea.get('name', '')}"]
        if idea.get("hotspot"):
            bits.append(f"热点「{idea['hotspot'][:36]}」")
        if idea.get("angle"):
            bits.append(f"角度：{idea['angle'][:40]}")
        for ln in (idea.get("lines") or [])[:2]:
            bits.append(f"梗「{ln[:28]}」")
        lines.append(f"  {i}. " + "；".join(bits))
    lines.append("新文案必须换全新的创意角度/梗/说法，禁止任何形式的重复或近似改写。")
    return "\n".join(lines)


def record_idea(template_id: str, template_name: str, hotspot_title: str,
                lines: dict | None, angle: str = "") -> None:
    """记录一条已用创意（lines: {seq: 台词}）"""
    ideas = load_ideas()
    # 去重：同模板+同热点若已存在则跳过
    key = (template_id, hotspot_title[:40])
    for i in ideas:
        if (i.get("template"), (i.get("hotspot") or "")[:40]) == key:
            return
    ideas.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "template": template_id,
        "name": template_name,
        "hotspot": hotspot_title,
        "angle": angle,
        "lines": list((lines or {}).values()),
    })
    IDEAS_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = IDEAS_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"ideas": ideas}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(IDEAS_STATE)


if __name__ == "__main__":
    print(f"已用创意 {len(load_ideas())} 条")
    print(ideas_block() or "（空）")
