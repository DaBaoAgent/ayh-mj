"""Read-only pre-production research for the template video pipeline.

Every storyboard gets a distinct, auditable brief from the local trend,
viral-video, short-drama and benchmark libraries before any generation starts.
"""
from __future__ import annotations

import re
from pathlib import Path

from .copybook import _load_bridges, structure_brief
from .ideas import used_hotspots
from .state import connect

ROOT = Path(__file__).resolve().parent.parent
TREND_LIBRARY = ROOT / "assets" / "trends" / "热点库.md"


def _trend_rows() -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id, platform, title, likes, comments, shares, score, "
            "matched, video_url, created_at FROM trends WHERE matched = 1 "
            "ORDER BY score DESC, likes DESC LIMIT 300"
        ).fetchall() if (row["title"] or "").strip()]


def _library_topics() -> list[dict]:
    if not TREND_LIBRARY.is_file():
        return []
    topics = []
    for line in TREND_LIBRARY.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*\d+\.\s+\[([^]]+)\].*?\|\s*(.+)$", line)
        if match:
            topics.append({"id": None, "platform": match.group(1),
                           "title": match.group(2).strip(), "score": 0,
                           "likes": 0, "video_url": ""})
    return topics


def _reference(row: dict) -> dict:
    return {"id": row.get("id"), "platform": row.get("platform"),
            "title": (row.get("title") or "")[:100],
            "likes": row.get("likes") or 0, "score": row.get("score") or 0,
            "url": row.get("video_url") or ""}


def research_inventory() -> dict:
    """Preflight the four knowledge sources without mutating rotation counters."""
    trends = _trend_rows() or _library_topics()
    bridges = [b for b in _load_bridges() if (b.get("pattern") or "").strip()]
    benchmark = [b for b in bridges if {"同行", "跨赛道"} & set(b.get("tags") or [])]
    drama = structure_brief(3000)
    missing = []
    if not trends:
        missing.append("热点库")
    if not any((r.get("likes") or 0) > 0 for r in trends) and not bridges:
        missing.append("爆款案例/桥段库")
    if not drama:
        missing.append("短剧结构库")
    if not benchmark:
        missing.append("同行/跨赛道对标桥段")
    return {"trends": len(trends), "bridges": len(bridges),
            "benchmarks": len(benchmark), "drama_chars": len(drama),
            "missing": missing}


def build_research_brief(exclude_titles: set[str] | None = None) -> dict:
    """Select a fresh topic and concrete references for one video."""
    inventory = research_inventory()
    if inventory["missing"]:
        raise RuntimeError("创作知识库不完整：" + "、".join(inventory["missing"]))
    excluded = used_hotspots() | (exclude_titles or set())
    rows = _trend_rows() or _library_topics()
    fresh = [row for row in rows if row["title"] not in excluded]
    if not fresh:
        raise RuntimeError("热点库没有未使用的选题；请补充新热点后再制作，避免重复旧片")
    # Prefer a current topic over an evergreen fallback, then high match score.
    fresh.sort(key=lambda row: (row.get("platform") == "evergreen", -(row.get("score") or 0)))
    primary = fresh[0]
    viral = sorted((r for r in rows if (r.get("likes") or 0) > 0 and r["title"] != primary["title"]),
                   key=lambda row: row.get("likes") or 0, reverse=True)[:4]
    bridges = [b for b in _load_bridges() if (b.get("pattern") or "").strip()]
    benchmark = [b for b in bridges if {"同行", "跨赛道"} & set(b.get("tags") or [])]
    drama_cases = [b for b in bridges if "短剧" in (b.get("tags") or [])]
    return {
        "hotspot": _reference(primary),
        "related_topics": [_reference(r) for r in fresh[1:5]],
        "viral_examples": [_reference(r) for r in viral],
        "short_drama_rules": structure_brief(3000),
        "short_drama_patterns": [{"title": b.get("title", ""), "pattern": b["pattern"]}
                                 for b in drama_cases[:3]],
        "benchmark_patterns": [{"title": b.get("title", ""), "tags": b.get("tags", []),
                                "pattern": b["pattern"]} for b in benchmark[:4]],
        "inventory": inventory,
    }
