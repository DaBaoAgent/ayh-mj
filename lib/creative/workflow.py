"""能力感知工作流路由（Phase 7 必做任务 8/9/10）。

为什么需要它：此前 spec 的 `workflow` / `fallback_workflows` 是**人工写死**的
（`storiespec.DEFAULT_WORKFLOW` + 两个常量），于是
  · 15s 的 spec 可能配一个只吃 1-10s 的工作流（提交即失败，白等 10 分钟）；
  · fallback 里混进不支持音频/参考图的型号 —— 主链失败后**悄悄丢掉音色锁定**，
    出一版不是同一个人声音的片，还当成功。
本模块把"选链"变成一次**能力校验**：需求（时长/图数/音频/首尾帧/片型风险）先从
spec 读出来，链条上每个工作流都必须满足全部需求，不满足的**直接拒绝**、绝不降级偷换。

唯一能力真源是 `s4_generate/workflow_router.WORKFLOW_SPECS`（2026-09-23 探测 + 官方核验），
这里不复制一份能力表 —— 复制就会过期。

对外 API（纯函数，可注入历史成功率以便离线测试）：
  Requirement / RoutePlan / WorkflowIncompatible
  requirements_from_spec(spec, ...)   读 spec → Requirement
  choose(req, *, known_ok=None)        Requirement → RoutePlan（首选 + 兼容 fallback 链）
  compatible(workflow, req)            单个工作流是否满足需求
  validate_chain(chain, req)           校验一条链，返回违规清单
  route_for_spec(spec, ...)            一步到位（planner 与编排器共用）
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── 能力真源（唯一）：s4_generate/workflow_router.py ───────────────
from s4_generate import workflow_router as _wr

WORKFLOW_SPECS: dict = _wr.WORKFLOW_SPECS
FALLBACK_CHAINS: dict = _wr.FALLBACK_CHAINS
QUALITY_RESOLUTION: dict = _wr.QUALITY_RESOLUTION
QUALITY_RESOLUTION_H: dict = _wr.QUALITY_RESOLUTION_H
PRICE_PER_SEC: dict = _wr.PRICE_PER_SEC

DEFAULT_QUALITY = "standard"
# 链条上限：主链 + 兜底最多这么长（再多也没有边际收益，只是多几次白等）
MAX_CHAIN = 4

_TIER_RANK = {"hq": 3, "standard": 2, "fast": 1}

# 简名 → 真名（s4_generate/autodl_client.WORKFLOWS 是唯一映射表；懒加载，避免
# import 期就去读供应商配置）。手写 spec / prep 脚本用的是简名（multi_image_15s…），
# 能力校验必须先把简名翻成真名，否则会误判成"未登记的工作流"。
_ALIAS_CACHE: dict[str, dict[str, str]] = {}


def canonical(workflow: str) -> str:
    """把工作流简名翻成能力表里的真名（无法识别就原样返回）。"""
    wf = str(workflow or "").strip()
    if not wf or wf in WORKFLOW_SPECS:
        return wf
    if "table" not in _ALIAS_CACHE:
        try:
            from s4_generate.autodl_client import WORKFLOWS as _W

            _ALIAS_CACHE["table"] = dict(_W)
        except Exception:      # noqa: BLE001 —— 拿不到映射就按真名处理
            _ALIAS_CACHE["table"] = {}
    return _ALIAS_CACHE.get("table", {}).get(wf, wf)


class WorkflowIncompatible(Exception):
    """没有任何工作流满足需求 —— 必须**拒绝**，绝不静默降级（任务 9）。"""

    error_code = "WORKFLOW_INCOMPATIBLE"

    def __init__(self, message: str, *, violations: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.violations = dict(violations or {})


@dataclass(frozen=True)
class Requirement:
    """一条 spec 对工作流的**硬需求**（丢了任何一项，片子就不是这条片）。"""

    duration: int = 15
    n_images: int = 0
    audio: bool = False            # 需要 ref_audio 音色锁定/音频参考
    first_last: bool = False       # 首尾帧模式
    text_only: bool = False        # 明确文生视频（无参考图）
    quality: str = DEFAULT_QUALITY
    risk: str = "low"
    vertical: bool = True
    prefer_hq: bool = False

    def to_dict(self) -> dict:
        return {"duration": self.duration, "n_images": self.n_images,
                "audio": self.audio, "first_last": self.first_last,
                "text_only": self.text_only, "quality": self.quality,
                "risk": self.risk, "vertical": self.vertical,
                "prefer_hq": self.prefer_hq}


@dataclass
class RoutePlan:
    """一次路由结果：首选 + 兼容 fallback 链 + 可解释理由。"""

    workflow: str
    fallbacks: list[str] = field(default_factory=list)
    resolution: str = "768p竖"
    cost_estimate: float = 0.0
    quality: str = DEFAULT_QUALITY
    requirement: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def chain(self) -> list[str]:
        return [self.workflow, *self.fallbacks]

    def to_dict(self) -> dict:
        return {"workflow": self.workflow, "fallbacks": list(self.fallbacks),
                "chain": self.chain, "resolution": self.resolution,
                "cost_estimate": self.cost_estimate, "quality": self.quality,
                "requirement": dict(self.requirement),
                "capabilities": dict(self.capabilities),
                "reasons": list(self.reasons), "rejected": list(self.rejected)}


# ── 能力校验 ─────────────────────────────────────────────────────
def compatible(workflow: str, req: Requirement) -> tuple[bool, str]:
    """这个工作流能不能**完整**满足需求？（返回 (ok, 不满足的原因)）"""
    spec = WORKFLOW_SPECS.get(canonical(workflow))
    if not spec:
        return False, f"{workflow} 不在能力表内（未探测过的型号不敢自动用）"
    kind = str(spec.get("kind") or "")
    lo, hi = spec["duration"]
    if not (lo <= req.duration <= hi):
        return False, f"{workflow} 时长 {lo}-{hi}s，装不下 {req.duration}s"
    if req.audio and not spec["audio"]:
        return False, f"{workflow} 不支持音频参考（音色锁定会丢）"
    # 反向同样要拦：以音频输入为前提的型号在无音频时"能提交但出不了片"，
    # 拿它当 fallback 只是多烧一次钱（2026-09-23 探测：zm 系列按 ref_audio 设计）。
    if not req.audio and "audio" in kind:
        return False, f"{workflow} 以音频输入为前提（kind={kind}），无音频时不出片"
    if req.n_images > spec["ref_images_max"]:
        return False, (f"{workflow} 最多 {spec['ref_images_max']} 张参考图，"
                       f"本条要 {req.n_images} 张")
    if req.first_last and kind != "first_last":
        return False, f"{workflow} 不是首尾帧模式（kind={kind}）"
    if req.text_only and spec["ref_images_max"] != 0:
        return False, f"{workflow} 需要参考图，不是纯文生"
    if not req.text_only and req.n_images > 0 and spec["ref_images_max"] == 0:
        return False, f"{workflow} 吃不下参考图（ref_images_max=0）"
    return True, ""


def validate_chain(chain: list[str], req: Requirement) -> list[dict]:
    """逐项校验一条链 —— 返回违规清单（空 = 链条上每一项都保住全部关键能力）。"""
    out: list[dict] = []
    for wf in chain:
        ok, why = compatible(wf, req)
        if not ok:
            out.append({"workflow": wf, "reason": why})
    return out


def _pop(workflow: str) -> float:
    raw = str((WORKFLOW_SPECS.get(workflow) or {}).get("pop_7d") or "0")
    mult = 1000.0 if raw.endswith("k") else 1.0
    try:
        return float(raw.rstrip("k")) * mult
    except ValueError:
        return 0.0


def _success(workflow: str, known_ok) -> float:
    """历史成功率（0..1）；调用方不传就当未知（0.5）。"""
    if not known_ok:
        return 0.5
    if isinstance(known_ok, dict):
        try:
            return float(known_ok.get(workflow, 0.5))
        except (TypeError, ValueError):
            return 0.5
    return 1.0 if workflow in set(known_ok) else 0.5


def _rank(workflow: str, known_ok) -> tuple:
    spec = WORKFLOW_SPECS.get(workflow) or {}
    return (-_success(workflow, known_ok), -_TIER_RANK.get(str(spec.get("tier") or ""), 0),
            -_pop(workflow))


def choose(req: Requirement, *, known_ok=None) -> RoutePlan:
    """需求 → RoutePlan。链条上每一项都通过 `compatible`（能力守恒，任务 9）。"""
    base = _wr.route(n_images=req.n_images, has_audio=req.audio, duration=req.duration,
                     first_last=req.first_last, text_only=req.text_only,
                     quality=req.quality, prefer_hq=req.prefer_hq)
    rejected: list[dict] = []
    kept: list[str] = []
    for wf in base:
        ok, why = compatible(wf, req)
        if ok:
            if wf not in kept:
                kept.append(wf)
        else:
            rejected.append({"workflow": wf, "reason": why})
    if not kept:
        raise WorkflowIncompatible(
            f"没有工作流能满足这条 spec 的硬需求：{req.to_dict()}；"
            f"候选全部被拒：{rejected}", violations=rejected)

    # 兜底补全：能力表里其它同样兼容的型号，按历史成功率/质量档/人气排序
    extras = [wf for wf in WORKFLOW_SPECS
              if wf not in kept and compatible(wf, req)[0]]
    extras.sort(key=lambda wf: _rank(wf, known_ok))
    keep_extras = [wf for wf in base if wf in kept]
    ordered = kept + [wf for wf in extras if wf not in keep_extras]
    chain = ordered[:MAX_CHAIN]
    primary = chain[0]
    spec = WORKFLOW_SPECS.get(primary) or {}
    reasons = [f"需求 {req.duration}s / {req.n_images} 图 / "
               f"音频={'要' if req.audio else '否'} / 首尾帧={'是' if req.first_last else '否'}",
               f"首选 {primary}（tier={spec.get('tier')}，kind={spec.get('kind')}）满足全部需求"]
    if len(chain) > 1:
        reasons.append("兼容 fallback：" + " > ".join(chain[1:]))
    if rejected:
        reasons.append(f"已排除 {len(rejected)} 个不兼容候选（绝不降级偷换能力）")
    return RoutePlan(
        workflow=primary, fallbacks=chain[1:],
        resolution=_wr.resolution_for(req.quality, vertical=req.vertical),
        cost_estimate=_cost(primary, req), quality=req.quality,
        requirement=req.to_dict(),
        capabilities=dict(WORKFLOW_SPECS.get(primary) or {}),
        reasons=reasons, rejected=rejected)


def _cost(workflow: str, req: Requirement) -> float:
    """按"实际输出分辨率"估成本；image_audio 系列不吃 resolution 参数，按档位估。"""
    res = _wr.resolution_for(req.quality, vertical=req.vertical)
    key = res[:res.index("p") + 1] if "p" in res else "768p"
    return round(PRICE_PER_SEC.get(key, 0.06) * int(req.duration), 3)


# ── 从 spec 读需求 ───────────────────────────────────────────────
def _view(spec) -> dict:
    if isinstance(spec, dict):
        creative = spec.get("creative") or {}
        return {"duration": int(spec.get("duration") or 15),
                "resolution": str(spec.get("resolution") or ""),
                "ref_images": list(spec.get("ref_images") or []),
                "ref_audios": list(spec.get("ref_audios") or []),
                "first_last": bool(spec.get("first_last")),
                "text_only": bool(spec.get("text_only")),
                "dna": dict(creative.get("dna") or spec.get("dna") or {})}
    return {"duration": int(getattr(spec, "duration", 15) or 15),
            "resolution": str(getattr(spec, "resolution", "") or ""),
            "ref_images": list(getattr(spec, "ref_images", None) or []),
            "ref_audios": list(getattr(spec, "ref_audios", None) or []),
            "first_last": bool(getattr(spec, "first_last", False)),
            "text_only": bool(getattr(spec, "text_only", False)),
            "dna": (getattr(spec, "dna", None).to_dict()
                    if getattr(spec, "dna", None) is not None else {})}


def requirements_from_spec(spec, *, quality: str | None = None, risk: str | None = None,
                           prefer_hq: bool | None = None) -> Requirement:
    """spec → 硬需求。quality 缺省从 resolution 反推（768p竖 → standard）。"""
    view = _view(spec)
    if quality is None:
        quality = _quality_of(view["resolution"])
    if prefer_hq is None:
        prefer_hq = quality == "premium"
    return Requirement(
        duration=view["duration"], n_images=len(view["ref_images"]),
        audio=bool(view["ref_audios"]), first_last=view["first_last"],
        text_only=view["text_only"], quality=quality,
        risk=risk or "low", vertical=not view["resolution"].endswith("横"),
        prefer_hq=bool(prefer_hq))


def _quality_of(resolution: str) -> str:
    for name, value in QUALITY_RESOLUTION.items():
        if value == resolution:
            return name
    for name, value in QUALITY_RESOLUTION_H.items():
        if value == resolution:
            return name
    return DEFAULT_QUALITY


def route_for_spec(spec, *, quality: str | None = None, risk: str | None = None,
                   known_ok=None) -> RoutePlan:
    """一步到位：spec → Requirement → RoutePlan（planner / 编排器共用）。"""
    req = requirements_from_spec(spec, quality=quality, risk=risk)
    return choose(req, known_ok=known_ok)


def within_budget(plan: RoutePlan, cap: float | None) -> bool:
    """预算内？（cap=None 视为不限）"""
    return True if cap is None else float(plan.cost_estimate) <= float(cap)
