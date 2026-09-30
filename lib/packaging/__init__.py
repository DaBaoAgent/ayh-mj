"""发布物料层（Phase 10）：PackagingAgent + 平台策略 + 发布 Gate。

对外四件事：
  · `build_brief()`   —— 把一份 spec 变成发布物料（标题候选/封面/描述/话题/首评/声明/目标）；
  · `materialize()`   —— 把 brief 落成某个平台的最终文案（按该平台字段上限裁剪）；
  · `check()`         —— 发布前 Gate（完整性 → AI 声明 → Claims 合规）；
  · `state`           —— packaging artifact 与"平台暂停"的唯一落盘位置。
"""
from __future__ import annotations

from .agent import (  # noqa: F401
    GENRE_TITLE_PREF,
    REQUIRED_FIELDS,
    TITLE_ANGLES,
    build_brief,
    claim_ids_of,
    materialize,
    validate,
)
from .gate import GateOutcome, claims_check, disclosure_check, publish_text  # noqa: F401
from .gate import check as publish_gate
from .platforms import (  # noqa: F401
    ALL_PLATFORMS,
    DOMESTIC,
    OVERSEAS,
    POLICIES,
    PlatformPolicy,
    channel_of,
    is_known,
    policy_for,
)
from .state import (  # noqa: F401
    load_brief,
    packaging_path,
    pause_platform,
    pause_reason,
    paused_platforms,
    resume_platform,
    save_brief,
    workspace_dir,
)

__all__ = [
    "ALL_PLATFORMS", "DOMESTIC", "GENRE_TITLE_PREF", "OVERSEAS", "POLICIES",
    "PlatformPolicy", "REQUIRED_FIELDS", "TITLE_ANGLES", "GateOutcome", "build_brief",
    "channel_of", "claim_ids_of", "claims_check", "disclosure_check", "is_known",
    "load_brief", "materialize", "packaging_path", "pause_platform", "pause_reason",
    "paused_platforms", "policy_for", "publish_gate", "publish_text", "resume_platform",
    "save_brief", "validate", "workspace_dir",
]
