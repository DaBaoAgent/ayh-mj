"""候选评分（Phase 5 必做任务 7 / 8 / 9）。

10 个维度（计划原文名，顺序即展示顺序）：
  Novelty / AudienceFit / TrendFit / SalesPointFit / VisualPotential /
  ConflictStrength / GenerationFeasibility / BrandSafety / ClaimRisk / EstimatedCost

**统一口径**：所有维度都换算成"越高越好"的 0..1 分（ClaimRisk / EstimatedCost 是负向
维度，用 `1 - 风险` / `1 - 成本` 表达），这样 `total = Σ weight × score` 不会因方向写反而失真。
每个维度都带一句人话理由，落进 artifact 后能回答"为什么是这个方案"。
"""
from __future__ import annotations

from .. import claims as claims_mod
from .. import products as products_mod
from .dna import CLAIM_RISK_FLAG, CreativeDNA

SCORE_DIMENSIONS: tuple[str, ...] = (
    "Novelty", "AudienceFit", "TrendFit", "SalesPointFit", "VisualPotential",
    "ConflictStrength", "GenerationFeasibility", "BrandSafety", "ClaimRisk", "EstimatedCost",
)
# 负向维度（原始量越大越差）；评分已取反，这里只用于解释与展示
NEGATIVE_DIMENSIONS: tuple[str, ...] = ("ClaimRisk", "EstimatedCost")

DIMENSION_WEIGHTS: dict[str, float] = {
    "Novelty": 0.14, "AudienceFit": 0.13, "TrendFit": 0.10, "SalesPointFit": 0.12,
    "VisualPotential": 0.10, "ConflictStrength": 0.10, "GenerationFeasibility": 0.11,
    "BrandSafety": 0.08, "ClaimRisk": 0.06, "EstimatedCost": 0.06,
}

# 骨架 → 天然贴合的受众（不是"只能给这些人看"，只是亲和度更高）
STRUCTURE_AUDIENCES: dict[str, tuple[str, ...]] = {
    "S_duo_conflict": ("子女代购决策者", "社区邻里围观者"),
    "S_solo_vlog": ("银发自用人群", "家庭照护者"),
    "S_street_interview": ("社区邻里围观者", "图文比价人群"),
    "S_suspense_reveal": ("子女代购决策者", "家庭照护者"),
    "S_magic_loop": ("社区邻里围观者", "银发自用人群"),
    "S_product_test": ("图文比价人群", "子女代购决策者"),
    "S_pov_first": ("银发自用人群", "家庭照护者"),
    "S_silent_slapstick": ("社区邻里围观者", "图文比价人群"),
    "S_emotional_story": ("子女代购决策者", "家庭照护者"),
    "S_comment_reply": ("图文比价人群", "社区邻里围观者"),
}

def _numeric_claim_points() -> frozenset[str]:
    """需要"数值/认证/质保/政策"核验的卖点 —— 由 Claims Registry 决定，不再硬编码。

    判据：卖点背后只要有一条 claim 不是「纯 feature 且已验证」，就算带承诺口径，
    ClaimRisk 需要扣分（Phase 5 的 CLAIM_RISK_FLAG 逻辑不变，只是名单改为注册表驱动）。
    注册表不可用时**保守**地把全部卖点视为待核验，绝不因为取不到数据就放松门禁。
    """
    try:
        reg = claims_mod.load()
    except Exception:
        return frozenset(products_mod.POINT_IDS)
    risky: set[str] = set()
    for point_id in products_mod.POINT_IDS:
        for claim_id in products_mod.claim_ids_for(point_id):
            claim = reg.get(claim_id)
            if (claim is None or claim.status != claims_mod.VERIFIED
                    or claim.kind != claims_mod.KIND_FEATURE
                    or claim.value not in ("", None)):
                risky.add(point_id)
                break
    return frozenset(risky)


# 数值承诺卖点清单（Phase 6 起唯一来源 = assets/products/claims.yaml）
NUMERIC_CLAIM_POINTS: frozenset[str] = _numeric_claim_points()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_dna(dna: CreativeDNA, *, structure: dict | None = None,
              context: dict | None = None) -> dict:
    """给一个候选 CreativeDNA 打分（10 维 + total + 逐维理由）。"""
    st = dict(structure or {})
    ctx = dict(context or {})
    used = ctx.get("used_counts") or {}
    day = ctx.get("day_registry") or {}
    trend = ctx.get("trend") or {}
    claim_points = set(ctx.get("claim_points") or NUMERIC_CLAIM_POINTS)
    reasons: dict[str, str] = {}

    # ① Novelty：池使用次数（保新优先）+ 同日重复惩罚
    novelty = 1.0
    counts_note = []
    for pool, key in (("genre", dna.genre), ("angle", dna.angle),
                      ("point", dna.sales_point), ("group", dna.cast_pattern)):
        n = int((used.get(pool) or {}).get(key, 0) or 0)
        if n:
            novelty -= min(0.18, 0.045 * n)
            counts_note.append(f"{pool}×{n}")
    if st.get("shot_pattern") and st["shot_pattern"] in (day.get("shot_patterns") or []):
        novelty -= 0.25
        counts_note.append("同日同镜头结构")
    if dna.genre and dna.genre in (day.get("genres") or []):
        novelty -= 0.18
        counts_note.append("同日同片型")
    if dna.hook_type in (day.get("hooks") or []):
        novelty -= 0.20
        counts_note.append("同日同钩子")
    if st.get("id") and st["id"] in (day.get("structures") or []):
        novelty -= 0.15
        counts_note.append("同日同骨架")
    if dna.cast_pattern and dna.cast_pattern in (day.get("cast") or []):
        novelty -= 0.15
        counts_note.append("同日同角色组合")
    reasons["Novelty"] = "历史使用 " + ("、".join(counts_note) if counts_note else "无（全新组合）")

    # ② AudienceFit：骨架 ↔ 受众亲和
    preferred = STRUCTURE_AUDIENCES.get(st.get("id", ""), ())
    audience_fit = 1.0 if dna.audience in preferred else 0.55
    reasons["AudienceFit"] = ("骨架天然受众" if audience_fit == 1.0 else "受众与骨架非最佳匹配")

    # ③ TrendFit：实时热点 > 常青素材；常青绝不当实时
    freshness = trend.get("freshness")
    relevance = float(trend.get("relevance") or 0.0)
    if trend.get("source_type") == "live":
        trend_fit = 0.72 + 0.28 * relevance
        if freshness is not None:
            trend_fit = 0.6 * trend_fit + 0.4 * float(freshness)
        reasons["TrendFit"] = f"实时热点（相关性 {relevance:.2f}，新鲜度 {freshness}）"
    else:
        trend_fit = 0.42 + 0.16 * relevance
        reasons["TrendFit"] = "常青素材（非实时热点，已标 source_type=evergreen）"

    # ④ SalesPointFit：产品角色与骨架一致 + 视觉母题落在演示段
    sales_fit = 1.0 if st.get("product_role") == dna.product_role else 0.68
    if st.get("visual_motif") and st["visual_motif"] == dna.visual_motif:
        sales_fit += 0.12
    reasons["SalesPointFit"] = (f"产品角色 {dna.product_role}"
                                + ("，母题与骨架一致" if st.get("visual_motif") == dna.visual_motif else ""))

    # ⑤ VisualPotential：骨架视觉潜力 + 是否给了具体视觉母题
    visual = 0.7 * float(st.get("visual_potential") or 0.5) + (0.3 if dna.visual_motif else 0.0)
    reasons["VisualPotential"] = f"骨架视觉潜力 {st.get('visual_potential', 0.5)}，母题 {dna.visual_motif or '未定'}"

    # ⑥ ConflictStrength：骨架冲突强度
    conflict = float(st.get("conflict_strength") or 0.5)
    reasons["ConflictStrength"] = f"骨架冲突强度 {conflict:.2f}"

    # ⑦ GenerationFeasibility：镜头数 / 角色数 / 成本系数 / 是否有台词
    cost_coef = float(st.get("generation_cost") or 0.5)
    cast_n = len([c for c in (dna.cast_pattern or "").split("+") if c.strip()]) or 1
    feasibility = 1.0 - 0.55 * cost_coef - 0.06 * (cast_n - 1)
    if dna.dialogue_mode == "无对白":
        feasibility += 0.10
    reasons["GenerationFeasibility"] = (f"成本系数 {cost_coef:.2f}，角色 {cast_n} 个，"
                                        f"台词模式 {dna.dialogue_mode}")

    # ⑧ BrandSafety：风险标签（不含数值承诺，那条单列）
    other_flags = [f for f in dna.risk_flags if f != CLAIM_RISK_FLAG]
    brand_safety = 1.0 - 0.30 * len(other_flags)
    reasons["BrandSafety"] = "无合规风险标签" if not other_flags else "风险标签：" + "、".join(other_flags)

    # ⑨ ClaimRisk（负向）：数值承诺待核验 → 分低
    claim_risk = 0.45 if (CLAIM_RISK_FLAG in dna.risk_flags or dna.sales_point in claim_points) else 1.0
    reasons["ClaimRisk"] = ("含数值/认证类承诺，须经 Claims Registry 核验后才可对外使用"
                            if claim_risk < 1.0 else "无未核验数值承诺")

    # ⑩ EstimatedCost（负向）：骨架成本系数取反
    est_cost = 1.0 - cost_coef
    reasons["EstimatedCost"] = f"相对制作成本 {cost_coef:.2f}"

    scores = {
        "Novelty": round(_clamp(novelty), 4),
        "AudienceFit": round(_clamp(audience_fit), 4),
        "TrendFit": round(_clamp(trend_fit), 4),
        "SalesPointFit": round(_clamp(sales_fit), 4),
        "VisualPotential": round(_clamp(visual), 4),
        "ConflictStrength": round(_clamp(conflict), 4),
        "GenerationFeasibility": round(_clamp(feasibility), 4),
        "BrandSafety": round(_clamp(brand_safety), 4),
        "ClaimRisk": round(_clamp(claim_risk), 4),
        "EstimatedCost": round(_clamp(est_cost), 4),
    }
    total = sum(DIMENSION_WEIGHTS[d] * scores[d] for d in SCORE_DIMENSIONS)
    return {**scores, "total": round(total, 4), "reasons": reasons}


def explain(score: dict, limit: int = 3) -> str:
    """把评分压成一句人话（artifact / event / 日志共用）。"""
    dims = {d: score.get(d, 0.0) for d in SCORE_DIMENSIONS}
    top = sorted(dims, key=lambda d: dims[d], reverse=True)[:limit]
    weak = sorted(dims, key=lambda d: dims[d])[:limit]
    return (f"总分 {score.get('total', 0):.3f}；强项 " + "、".join(f"{d}{dims[d]:.2f}" for d in top)
            + "；弱项 " + "、".join(f"{d}{dims[d]:.2f}" for d in weak))
