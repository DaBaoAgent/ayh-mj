"""平台发布策略表（Phase 10 任务 6/7）。

一张表回答四件事（三处各写一份就会漂移，所以只在这里写）：
  · 这个平台走哪条通道（国内 PostFlow / 海外 Upload-Post）；
  · 是否**强制** AI 生成内容声明；
  · 能不能"只上传草稿"（不能的话就无法在声明不可确认时安全落地 → 交人工）；
  · 标题/描述/话题的字段上限。

`requires_ai_disclosure=True` 且 `supports_draft=False` 时，自动化**不允许**真发：
只能进入 `REQUIRE_HUMAN_PUBLISH`。这正是计划 §Phase 10 任务 7 的口径。
"""
from __future__ import annotations

from dataclasses import dataclass

DOMESTIC = ("douyin", "xiaohongshu", "shipinhao")
OVERSEAS = ("tiktok", "youtube", "instagram", "facebook", "telegram", "x")
ALL_PLATFORMS = DOMESTIC + OVERSEAS

# 草稿语义（supports_draft=True 时必须说明"草稿"到底怎么实现，避免口头承诺）：
#   douyin/xiaohongshu/shipinhao → PostFlow 草稿箱，不进入公开推荐流；
#   tiktok                      → Upload-Post MEDIA_UPLOAD（进创作者收件箱，未发布）；
#   youtube                     → privacy=private（仅自己可见，等同草稿）。
DRAFT_MECHANISM = {
    "douyin": "postflow_draft",
    "xiaohongshu": "postflow_draft",
    "shipinhao": "postflow_draft",
    "tiktok": "MEDIA_UPLOAD",
    "youtube": "privacy=private",
}


@dataclass(frozen=True)
class PlatformPolicy:
    """单个平台的发布约束。"""

    name: str
    channel: str                 # domestic | overseas
    requires_ai_disclosure: bool
    supports_draft: bool
    supports_direct: bool
    max_title_chars: int
    max_description_chars: int
    max_hashtags: int
    draft_mechanism: str = ""

    def to_dict(self) -> dict:
        return {
            "platform": self.name, "channel": self.channel,
            "requires_ai_disclosure": self.requires_ai_disclosure,
            "supports_draft": self.supports_draft, "supports_direct": self.supports_direct,
            "max_title_chars": self.max_title_chars,
            "max_description_chars": self.max_description_chars,
            "max_hashtags": self.max_hashtags,
            "draft_mechanism": self.draft_mechanism,
        }


POLICIES: dict[str, PlatformPolicy] = {
    "douyin": PlatformPolicy("douyin", "domestic", True, True, True, 55, 1000, 5,
                             DRAFT_MECHANISM["douyin"]),
    "xiaohongshu": PlatformPolicy("xiaohongshu", "domestic", True, True, True, 20, 1000, 10,
                                  DRAFT_MECHANISM["xiaohongshu"]),
    "shipinhao": PlatformPolicy("shipinhao", "domestic", True, True, True, 22, 1000, 5,
                                DRAFT_MECHANISM["shipinhao"]),
    "tiktok": PlatformPolicy("tiktok", "overseas", True, True, True, 100, 2200, 10,
                             DRAFT_MECHANISM["tiktok"]),
    "youtube": PlatformPolicy("youtube", "overseas", True, True, True, 100, 5000, 15,
                              DRAFT_MECHANISM["youtube"]),
    # 没有"草稿"概念的平台：AI 声明确认不了就只能交人工，不能真发。
    "instagram": PlatformPolicy("instagram", "overseas", True, False, True, 100, 2200, 30),
    "facebook": PlatformPolicy("facebook", "overseas", True, False, True, 100, 5000, 10),
    "telegram": PlatformPolicy("telegram", "overseas", True, False, True, 100, 4000, 5),
    "x": PlatformPolicy("x", "overseas", True, False, True, 100, 280, 5),
}


def policy_for(platform: str) -> PlatformPolicy | None:
    return POLICIES.get(str(platform or "").strip().lower())


def is_known(platform: str) -> bool:
    return policy_for(platform) is not None


def channel_of(platform: str) -> str:
    policy = policy_for(platform)
    return policy.channel if policy else "unknown"
