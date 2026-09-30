"""热点归一化（Phase 5 必做任务 3 / 4）。

任何来源的热点进 Planner 之前都要过这里，统一成同一组字段：
`来源 / 标题 / 发布时间 / 热度 / 互动 / 相关性 / 新鲜度 / 证据 URL`。

**source_type 是硬分界**：`live` = 有互动量且有发布时间的实时热点；
`evergreen` = 常青素材 / 知识库条目。常青素材永远不许冒充"实时热点"——
没有发布日期就不许标 live（宁可标常青，也不许假装新鲜）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SOURCE_TYPES = ("live", "evergreen")
# 这些平台/来源标记一律算常青素材
EVERGREEN_PLATFORMS = ("evergreen", "library", "常青", "常青素材", "知识库")
FRESH_WINDOW_HOURS = 24 * 30     # 30 天外的新鲜度记 0
LIBRARY_PREFIX = "library://"

# 归一化后必须齐全的字段（验收：来源/标题/发布时间/热度/互动/相关性/新鲜度/证据URL）
NORMALIZED_FIELDS: tuple[str, ...] = (
    "source", "source_type", "title", "published_at", "heat",
    "engagement", "relevance", "freshness", "evidence_url",
)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")[:19])
    except ValueError:
        return None


def freshness_of(published_at, *, now: datetime | None = None) -> float | None:
    """新鲜度 0..1（越新越高）；没有发布时间 → None（不假装新鲜）。"""
    dt = _parse_dt(published_at)
    if dt is None:
        return None
    now = now or datetime.now()
    age = max(0.0, (now - dt).total_seconds() / 3600.0)
    if age >= FRESH_WINDOW_HOURS:
        return 0.0
    return round(1.0 - age / FRESH_WINDOW_HOURS, 4)


def is_evergreen_platform(platform: str) -> bool:
    return (platform or "").strip().lower() in EVERGREEN_PLATFORMS


@dataclass(frozen=True)
class Hotspot:
    """归一化热点（不可变，便于当 artifact 落盘与做幂等键）。"""

    source: str = ""
    source_type: str = "evergreen"
    title: str = ""
    published_at: str = ""
    heat: float = 0.0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    relevance: float = 0.0
    freshness: float | None = None
    evidence_url: str = ""
    extras: dict = field(default_factory=dict)

    @property
    def engagement(self) -> int:
        return int(self.likes + self.comments + self.shares)

    @property
    def is_evergreen(self) -> bool:
        return self.source_type == "evergreen"

    def to_dict(self) -> dict:
        return {
            "source": self.source, "source_type": self.source_type, "title": self.title,
            "published_at": self.published_at, "heat": self.heat,
            "engagement": self.engagement, "relevance": self.relevance,
            "freshness": self.freshness, "evidence_url": self.evidence_url,
            "likes": self.likes, "comments": self.comments, "shares": self.shares,
            "is_evergreen": self.is_evergreen,
        }


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def normalize_hotspot(row: dict, *, library_ref: str = "",
                      now: datetime | None = None) -> Hotspot:
    """任意来源（trends 表行 / 热点库条目）→ 结构化 Hotspot。"""
    row = dict(row or {})
    platform = str(row.get("platform") or row.get("source") or "")
    title = str(row.get("title") or "").strip()
    likes, comments, shares = _int(row.get("likes")), _int(row.get("comments")), _int(row.get("shares"))
    published = str(row.get("created_at") or row.get("published_at") or "").strip()
    url = str(row.get("video_url") or row.get("url") or row.get("evidence_url") or "").strip()
    ref = str(row.get("ref") or library_ref or "").strip()
    score = row.get("score")
    try:
        heat = float(score) if score else float(likes + comments + shares)
    except (TypeError, ValueError):
        heat = float(likes + comments + shares)

    # 只有"有互动量 + 有可解析发布时间 + 非常青平台"才算实时热点
    live_signal = (
        not is_evergreen_platform(platform)
        and (likes or comments or shares)
        and _parse_dt(published) is not None
    )
    source_type = "live" if live_signal else "evergreen"

    if row.get("matched") is not None:
        relevance = 1.0 if row.get("matched") else 0.3
    elif score:
        relevance = min(1.0, float(heat) / 100.0)
    else:
        relevance = 0.6          # 知识库精选条目：人工挑过，按中等相关起步

    evidence = url or (LIBRARY_PREFIX + ref if ref else "")
    return Hotspot(
        source=platform, source_type=source_type, title=title, published_at=published,
        heat=heat, likes=likes, comments=comments, shares=shares,
        relevance=relevance, freshness=freshness_of(published, now=now),
        evidence_url=evidence, extras={"ref": ref} if ref else {},
    )
