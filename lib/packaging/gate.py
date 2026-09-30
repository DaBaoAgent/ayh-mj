"""发布 Gate（Phase 10 任务 6/8）—— 发布前最后一道不可绕过的门。

三件事，任何一条不过就不许"真发"：
  ① packaging artifact 完整性（标题/描述/话题/声明字段/目标平台都必须有）；
  ② 发布文案过 Claims 合规门（标题、描述、话题、首评里出现未登记 claim 即拦）；
  ③ AI 生成内容声明是**硬字段**：声明无法程序化确认时，该平台只能草稿或转人工，
     绝不允许 direct。

Gate 返回结构化 error_code，交给 PublishService 决定是"转人工"还是"记失败"。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..orchestrator.errors import (
    AI_DISCLOSURE_UNCONFIRMED,
    CLAIM_FORBIDDEN,
    CLAIM_NEEDS_VERIFICATION,
    CLAIM_UNMAPPED,
    PACKAGING_INCOMPLETE,
    REQUIRE_HUMAN_PUBLISH,
)

CHANNEL = "packaging"


@dataclass
class GateOutcome:
    ok: bool
    code: str = ""
    message: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "error_code": self.code or None,
                "message": self.message, "data": self.data}


def publish_text(brief: dict) -> str:
    """所有"会给平台/观众看到"的文字（合规门只扫这些）。"""
    parts: list[str] = [str(brief.get("title") or ""), str(brief.get("title_reason") or "")]
    for cand in (brief.get("title_candidates") or []):
        if isinstance(cand, dict):
            parts.append(str(cand.get("text") or ""))
    parts.append(str(brief.get("description") or ""))
    parts.extend(str(t) for t in (brief.get("hashtags") or []))
    parts.extend(str(c) for c in (brief.get("first_comment_candidates") or []))
    cover = brief.get("cover") or {}
    if isinstance(cover, dict):
        parts.append(str(cover.get("text") or ""))
    return "\n".join(p for p in parts if p)


def claims_check(text: str, channel: str = CHANNEL) -> tuple[str, str, dict]:
    """→ (error_code, message, metrics)；error_code 为空 = 通过。"""
    from .. import claims as claims_mod

    if not text.strip():
        return "", "", {"claims_gate": "empty"}
    try:
        result = claims_mod.gate(text, channel)
    except claims_mod.RegistryError as exc:
        return (CLAIM_UNMAPPED, f"Claims Registry 不可用，无法校验发布文案：{exc}",
                {"claims_gate": "registry_error"})
    metrics = {"claims_gate": "pass" if result.ok else "block",
               "claim_ids": list(result.claim_ids or []),
               "unmapped": len(result.unmapped), "blocked": len(result.blocked)}
    if result.ok:
        return "", "", metrics
    kinds = {f.kind for f in result.unmapped} | {f.kind for f in result.blocked}
    forbidden = any("forbidden" in (f.blocked_reason or "") for f in result.blocked)
    if "forbidden_rewrite" in kinds or forbidden:
        code = CLAIM_FORBIDDEN
    elif result.unmapped:
        code = CLAIM_UNMAPPED
    else:
        code = CLAIM_NEEDS_VERIFICATION
    return code, f"发布文案未过合规门：{result.message()}", metrics


def disclosure_check(brief: dict, platforms: list[str] | None = None) -> tuple[str, str, dict]:
    """AI 声明硬门：不确认就必须草稿；没有草稿通道就直接转人工。"""
    targets = brief.get("targets") or []
    wanted = set(platforms or [t.get("platform") for t in targets])
    per: dict[str, dict] = {}
    for t in targets:
        platform = str(t.get("platform") or "")
        if platform not in wanted:
            continue
        mode = str(t.get("mode") or "")
        requires = bool(t.get("requires_ai_disclosure"))
        confirmable = bool(t.get("ai_disclosure_confirmable"))
        if not requires:
            verdict = "ok"
        elif mode == "direct" and not confirmable:
            verdict = "unconfirmed_direct"      # 声明没确认却要走直发 → 拦
        elif mode == "require_human":
            verdict = "no_draft_channel"
        elif mode == "draft":
            verdict = "draft_ok"
        else:
            verdict = "ok"
        per[platform] = {"mode": mode, "requires_ai_disclosure": requires,
                         "confirmable": confirmable, "verdict": verdict}
    bad = {p: v for p, v in per.items() if v["verdict"] == "unconfirmed_direct"}
    human = {p: v for p, v in per.items() if v["verdict"] == "no_draft_channel"}
    if bad:
        names = "、".join(sorted(bad))
        return (AI_DISCLOSURE_UNCONFIRMED,
                f"AI 生成内容声明无法确认，拒绝直发：{names}", {"disclosure": per})
    if human:
        names = "、".join(sorted(human))
        return (REQUIRE_HUMAN_PUBLISH,
                f"AI 声明无法确认且平台无草稿通道，需人工发布：{names}", {"disclosure": per})
    return "", "", {"disclosure": per}


def check(brief: dict | None, *, platforms: list[str] | None = None) -> GateOutcome:
    """发布前完整 Gate（顺序：完整性 → 声明 → 合规）。"""
    from .agent import validate

    problems = validate(brief)
    if problems:
        return GateOutcome(False, PACKAGING_INCOMPLETE,
                           "packaging artifact 不完整：" + "；".join(problems),
                           {"problems": problems})

    code, message, data = disclosure_check(brief, platforms)
    if code:
        return GateOutcome(False, code, message, data)

    code, message, metrics = claims_check(publish_text(brief))
    if code:
        return GateOutcome(False, code, message, metrics)

    # direct 只对"声明已确认或无需声明"的平台放行；draft 走草稿；其余转人工。
    modes = {t.get("platform"): t.get("mode") for t in (brief.get("targets") or [])}
    if not modes:
        return GateOutcome(False, PACKAGING_INCOMPLETE, "packaging 没有发布目标",
                           {"problems": ["targets 为空"]})
    return GateOutcome(True, "", "发布 Gate 通过", {"modes": modes, **metrics, **data})
