"""Claims Service —— 产品事实的**唯一**读取入口（Phase 6 必做任务 3）。

设计约束
  · 权威事实只在 `assets/products/claims.yaml`。Script / Packaging / Engage 一律经本模块
    读取，禁止任何地方再内置第二套参数（旧的 `products.py` 文案、`engage.py` 的
    PRODUCT_POINTS 都已改成从这里取）。
  · 三态 status：`verified` 可自动使用；`needs_verification` 口径冲突/缺材料，**禁止自动
    对外使用**（任务 2）；`forbidden` 法规禁止自动生成（任务 5）。
  · `gate()` 是合规门：LLM 产出的文本里出现数值/认证/质保/疗效/绝对化表述时，必须能映射到
    claim_id，否则 Gate 不通过（任务 4）。映射失败绝不"看起来合理就放行"。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "assets" / "products" / "claims.yaml"
DEFAULT_SKU = "ainsnbot_x218"

CHANNELS: tuple[str, ...] = ("script", "packaging", "engage", "cover", "subtitle")
CHANNEL_LABELS = {"script": "脚本台词", "packaging": "发布文案", "engage": "互动回复",
                  "cover": "封面", "subtitle": "字幕"}

VERIFIED = "verified"
NEEDS_VERIFICATION = "needs_verification"
FORBIDDEN = "forbidden"
STATUSES: tuple[str, ...] = (VERIFIED, NEEDS_VERIFICATION, FORBIDDEN)

KIND_NUMBER = "number"
KIND_CERTIFICATION = "certification"
KIND_WARRANTY = "warranty"
KIND_MEDICAL = "medical"
KIND_SUPERLATIVE = "superlative"
KIND_FEATURE = "feature"
KIND_SERVICE = "service"
KIND_POLICY = "policy"
KIND_POSITIONING = "positioning"
KINDS: tuple[str, ...] = (KIND_NUMBER, KIND_CERTIFICATION, KIND_WARRANTY, KIND_MEDICAL,
                         KIND_SUPERLATIVE, KIND_FEATURE, KIND_SERVICE, KIND_POLICY,
                         KIND_POSITIONING)

# 计划要求的 13 个必填字段（其余为 Phase 6 扩展字段）
REQUIRED_FIELDS: tuple[str, ...] = (
    "claim_id", "sku", "display_text", "spoken_text", "value", "unit", "evidence",
    "certificate", "valid_from", "valid_to", "allowed_channels", "risk_level",
    "forbidden_rewrites",
)
OPTIONAL_FIELDS: tuple[str, ...] = ("kind", "status", "numeric_tokens", "keywords", "notes")
ALL_FIELDS: tuple[str, ...] = REQUIRED_FIELDS + OPTIONAL_FIELDS

# ── 检测规则（任务 4/5 的"必须映射到 claim_id"清单）──────────────────────
CN_NUM = "零一二三四五六七八九十百千万两〇"
_NUM = rf"(?:\d+(?:\.\d+)?|[{CN_NUM}]+(?:点[{CN_NUM}]+)?)"
UNITS = ("kg", "公斤", "千克", "km/h", "km", "公里", "千米", "cm", "公分", "厘米",
         "米", "m", "度", "°", "股", "项", "年", "天", "分钟", "A", "安", "W", "瓦", "%")
# 单位后面不许再跟字母/数字：否则 `85mm 镜头`（摄影参数，不是产品参数）会被读成 "85m"。
_NUMERIC_RE = re.compile(rf"{_NUM}\s*(?:{'|'.join(re.escape(u) for u in UNITS)})(?![A-Za-z0-9])")

# 关键词组 → 对应 claim.kind；命中后必须在同 kind 的 claim 里找到唯一归属
GROUP_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (KIND_CERTIFICATION, re.compile(
        r"认证|专利|医疗器械|CNAS|UN[_ ]?38\.3|资质|备案|医疗级", re.I)),
    (KIND_WARRANTY, re.compile(r"质保|保修|售后|终身")),
    (KIND_MEDICAL, re.compile(r"治疗|治愈|疗效|康复|医用|药效|包治|能不能治|病人能用")),
    (KIND_SUPERLATIVE, re.compile(
        r"最好|最佳|最强|最快|最轻|最安全|最便宜|最省|唯一|绝对|100\s*%|顶级|"
        r"永不|全能|销量王|"
        # "第一" 只有在**不是**序数/机位/时间语时才算广告法绝对化用语：
        # "POV 第一人称"是镜头语言，报出来是误伤（Phase 7 集成实测）。
        r"第一(?!人称|视角|次|天|时间|步|现场|次见面)")),
)

_WS_RE = re.compile(r"\s+")

# 单位等价（同口径的不同写法必须互相命中："13.8公斤" == "13.8kg"）
_UNIT_CANON: dict[str, str] = {
    "kg": "kg", "公斤": "kg", "千克": "kg",
    "km/h": "km/h", "公里/小时": "km/h",
    "km": "km", "公里": "km", "千米": "km",
    "cm": "cm", "公分": "cm", "厘米": "cm",
    "m": "m", "米": "m",
    "度": "度", "°": "度",
    "股": "股", "项": "项", "年": "年", "天": "天", "分钟": "分钟",
    "a": "A", "安": "A", "w": "W", "瓦": "W",
    "%": "%", "％": "%", "秒": "秒",
}
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _canon_unit(unit: str) -> str:
    key = _norm(unit)
    return _UNIT_CANON.get(key, key)


def _cn_number(text: str) -> str | None:
    """中文数字 → 阿拉伯数字字符串（"十三点八" → "13.8"）。不认识返回 None。"""
    s = str(text or "")
    if not s:
        return None
    head, _, frac = s.partition("点")
    total, section, last = 0, 0, 0
    for ch in head:
        if ch in _CN_DIGITS:
            last = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            scale = _CN_UNITS[ch]
            if scale == 10000:
                section = (section + (last or 1)) * scale
                total += section
                section, last = 0, 0
                continue
            section += (last or 1) * scale
            last = 0
        else:
            return None
    value = total + section + last
    out = str(value)
    if frac:
        digits = ""
        for ch in frac:
            if ch not in _CN_DIGITS:
                return None
            digits += str(_CN_DIGITS[ch])
        out = f"{out}.{digits}"
    return out


def _canon_numeric(token: str) -> str | None:
    """"十三点八公斤" → "13.8kg"；"360°" → "360度"；不含单位则只归一数字。"""
    s = _norm(token)
    if not s:
        return None
    m = re.match(rf"^({_NUM})(.*)$", s)
    if not m:
        return None
    raw_num, raw_unit = m.group(1), m.group(2)
    num = _cn_number(raw_num) if re.match(rf"^[{CN_NUM}]", raw_num) else raw_num
    if num is None:
        return None
    num = num.rstrip("0").rstrip(".") if ("." in num and num.endswith("0")) else num
    return f"{num}{_canon_unit(raw_unit)}" if raw_unit else num


def _norm(text: str) -> str:
    """比较用的归一：去空白、大小写统一、全角百分号→半角。"""
    return _WS_RE.sub("", str(text or "").lower().replace("％", "%"))


def _today() -> _dt.date:
    return _dt.date.today()


def _as_date(value) -> _dt.date | None:
    if not value:
        return None
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class Claim:
    """一条产品事实（机器可读的唯一权威来源）。"""

    claim_id: str
    sku: str = DEFAULT_SKU
    display_text: str = ""
    spoken_text: str = ""
    value: object = ""
    unit: str = ""
    evidence: str = ""
    certificate: str = ""
    valid_from: str = ""
    valid_to: str = ""
    allowed_channels: tuple[str, ...] = ()
    risk_level: str = "low"
    forbidden_rewrites: tuple[str, ...] = ()
    kind: str = KIND_FEATURE
    status: str = VERIFIED
    numeric_tokens: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    notes: str = ""

    # ── 可用性 ──────────────────────────────────────────────
    def in_window(self, on: _dt.date | None = None) -> bool:
        on = on or _today()
        start, end = _as_date(self.valid_from), _as_date(self.valid_to)
        return (start is None or start <= on) and (end is None or on <= end)

    def allows(self, channel: str) -> bool:
        return str(channel or "").lower() in {c.lower() for c in self.allowed_channels}

    def usable(self, channel: str = "", on: _dt.date | None = None) -> bool:
        """能否自动对外使用：verified + 在有效期内 + 该渠道允许。"""
        return self.status == VERIFIED and self.in_window(on) and (not channel or self.allows(channel))

    def block_reason(self, channel: str = "", on: _dt.date | None = None) -> str:
        if self.status == NEEDS_VERIFICATION:
            return f"口径待核验（needs_verification）：{self.notes or '存在冲突/缺证据'}"
        if self.status == FORBIDDEN:
            return f"禁止自动使用（forbidden）：{self.notes or '合规红线'}"
        if not self.in_window(on):
            return f"不在有效期（valid_from={self.valid_from} valid_to={self.valid_to}）"
        if channel and not self.allows(channel):
            return f"渠道不允许（allowed_channels={list(self.allowed_channels)}）"
        return ""

    def tokens(self) -> tuple[str, ...]:
        out = list(self.numeric_tokens) + list(self.keywords)
        if self.value not in ("", None) and self.unit:
            out.append(f"{self.value}{self.unit}")
        return tuple(out)

    def to_dict(self) -> dict:
        return {"claim_id": self.claim_id, "sku": self.sku, "kind": self.kind,
                "status": self.status, "display_text": self.display_text,
                "spoken_text": self.spoken_text, "value": self.value, "unit": self.unit,
                "evidence": self.evidence, "certificate": self.certificate,
                "valid_from": self.valid_from, "valid_to": self.valid_to,
                "allowed_channels": list(self.allowed_channels),
                "risk_level": self.risk_level, "forbidden_rewrites": list(self.forbidden_rewrites),
                "numeric_tokens": list(self.numeric_tokens), "keywords": list(self.keywords),
                "notes": self.notes}


def _claim_from_row(row: dict) -> Claim:
    data = {k: row.get(k) for k in ALL_FIELDS}
    for key, default in (("allowed_channels", ()), ("forbidden_rewrites", ()),
                         ("numeric_tokens", ()), ("keywords", ())):
        value = data.get(key) or default
        data[key] = tuple(value) if not isinstance(value, str) else (value,)
    data["claim_id"] = str(data.get("claim_id") or "").strip()
    data["sku"] = str(data.get("sku") or DEFAULT_SKU)
    data["kind"] = str(data.get("kind") or KIND_FEATURE)
    data["status"] = str(data.get("status") or VERIFIED)
    data["risk_level"] = str(data.get("risk_level") or "low")
    for key in ("display_text", "spoken_text", "unit", "evidence", "certificate",
                "valid_from", "valid_to", "notes"):
        data[key] = str(data.get(key) or "")
    return Claim(**data)


class RegistryError(ValueError):
    """claims.yaml 结构不合法（缺字段/重复 id/未知 status）。"""


@dataclass
class ClaimsRegistry:
    """claims.yaml 的内存视图（只读）。"""

    claims: dict[str, Claim] = field(default_factory=dict)
    sku: str = DEFAULT_SKU
    product: str = ""
    version: int = 1
    updated_at: str = ""
    evidence_doc: str = ""
    path: Path = DEFAULT_PATH

    # ── 查询 ────────────────────────────────────────────────
    def __contains__(self, claim_id: str) -> bool:
        return claim_id in self.claims

    def __len__(self) -> int:
        return len(self.claims)

    def get(self, claim_id: str) -> Claim | None:
        return self.claims.get(str(claim_id or ""))

    def all(self) -> list[Claim]:
        return list(self.claims.values())

    def by_status(self, status: str) -> list[Claim]:
        return [c for c in self.all() if c.status == status]

    def by_kind(self, kind: str) -> list[Claim]:
        return [c for c in self.all() if c.kind == kind]

    def status_counts(self) -> dict[str, int]:
        return {s: len(self.by_status(s)) for s in STATUSES}

    def verified(self) -> list[Claim]:
        return self.by_status(VERIFIED)

    def needs_verification(self) -> list[Claim]:
        return self.by_status(NEEDS_VERIFICATION)

    def forbidden(self) -> list[Claim]:
        return self.by_status(FORBIDDEN)

    def usable(self, channel: str = "", on: _dt.date | None = None) -> list[Claim]:
        return [c for c in self.all() if c.usable(channel, on)]

    def numeric_claims(self) -> list[Claim]:
        return [c for c in self.all() if c.kind == KIND_NUMBER]

    def digest(self) -> str:
        """注册表指纹：任何口径/sku/有效期变化都会改变它（供 regression test）。"""
        payload = [c.to_dict() for c in sorted(self.all(), key=lambda c: c.claim_id)]
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ── 面向下游的文本块 ────────────────────────────────────
    def facts_block(self, channel: str = "", on: _dt.date | None = None) -> str:
        """只含"可自动使用"的 claim 的事实块（给 LLM 当唯一产品信息源）。"""
        rows: list[str] = []
        for c in self.usable(channel, on):
            text = c.spoken_text or c.display_text
            if not text:
                continue
            extra = f"（{c.value}{c.unit}）" if c.value not in ("", None) and c.unit else ""
            rows.append(f"- {text}{extra} [claim:{c.claim_id}]")
        return "\n".join(rows)

    def blocked_block(self, on: _dt.date | None = None) -> str:
        """需人工核对 / 禁止自动使用的事实清单（给人看，不进 prompt）。"""
        rows: list[str] = []
        for c in self.all():
            if c.status == VERIFIED:
                continue
            rows.append(f"- [{c.status}] {c.claim_id}: {c.display_text or c.kind} —— {c.notes}")
        return "\n".join(rows)


# ── 装载 / 校验 ──────────────────────────────────────────────
_CACHE: dict[str, tuple[float, ClaimsRegistry]] = {}


def _read_doc(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RegistryError(f"claims 注册表不存在：{path}") from exc
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(f"claims.yaml 不是合法 YAML：{exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("claims"), list):
        raise RegistryError("claims.yaml 顶层必须是映射，且含一个 claims 列表")
    return doc


def validate_doc(doc: dict) -> list[str]:
    """结构校验（不抛异常，返回问题清单；供测试与 --check 使用）。"""
    problems: list[str] = []
    rows = doc.get("claims") or []
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"claims[{i}] 不是映射")
            continue
        cid = str(row.get("claim_id") or "")
        where = cid or f"claims[{i}]"
        if not cid:
            problems.append(f"claims[{i}] 缺少 claim_id")
        elif cid in seen:
            problems.append(f"{where} claim_id 重复")
        seen.add(cid)
        for key in REQUIRED_FIELDS:
            if key not in row:
                problems.append(f"{where} 缺少必填字段 {key}")
        for key in row:
            if key not in ALL_FIELDS:
                problems.append(f"{where} 含未知字段 {key}")
        status = str(row.get("status") or VERIFIED)
        if status not in STATUSES:
            problems.append(f"{where} 非法 status={status}")
        kind = str(row.get("kind") or KIND_FEATURE)
        if kind not in KINDS:
            problems.append(f"{where} 非法 kind={kind}")
        channels = row.get("allowed_channels")
        if channels is not None and not isinstance(channels, list):
            problems.append(f"{where} allowed_channels 必须是列表")
        for ch in channels or []:
            if ch not in CHANNELS:
                problems.append(f"{where} 未知渠道 {ch}")
        rewrites = row.get("forbidden_rewrites")
        if rewrites is not None and not isinstance(rewrites, list):
            problems.append(f"{where} forbidden_rewrites 必须是列表")
        if status == VERIFIED:
            if not (row.get("evidence") or ""):
                problems.append(f"{where} verified 但没有 evidence")
            if kind in (KIND_NUMBER, KIND_SUPERLATIVE) and not str(row.get("value") or ""):
                problems.append(f"{where} {kind} 类 claim 必须有 value")
            if kind == KIND_NUMBER and not str(row.get("unit") or ""):
                problems.append(f"{where} number 类 claim 必须有 unit")
    return problems


def load(path: Path | str | None = None, *, force: bool = False) -> ClaimsRegistry:
    """装载注册表（带 mtime 缓存）；结构非法直接 RegistryError，绝不静默带病运行。"""
    p = Path(path) if path else DEFAULT_PATH
    key = str(p.resolve())
    try:
        mtime = p.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    cached = _CACHE.get(key)
    if cached and not force and cached[0] == mtime:
        return cached[1]
    doc = _read_doc(p)
    problems = validate_doc(doc)
    if problems:
        raise RegistryError("claims.yaml 校验失败：\n  - " + "\n  - ".join(problems))
    reg = ClaimsRegistry(claims={}, sku=str(doc.get("sku") or DEFAULT_SKU),
                         product=str(doc.get("product") or ""),
                         version=int(doc.get("version") or 1),
                         updated_at=str(doc.get("updated_at") or ""),
                         evidence_doc=str(doc.get("evidence_doc") or ""), path=p)
    for row in doc.get("claims") or []:
        claim = _claim_from_row(row)
        reg.claims[claim.claim_id] = claim
    _CACHE[key] = (mtime, reg)
    return reg


def registry(path: Path | str | None = None, *, force: bool = False) -> ClaimsRegistry:
    """便捷别名（下游统一用这个）。"""
    return load(path, force=force)


# ── 扫描 / 合规门（任务 4/5）─────────────────────────────────
@dataclass(frozen=True)
class Finding:
    """一处需要 claim 背书的表述。"""

    kind: str                 # numeric | forbidden_rewrite | certification | warranty | medical | superlative
    text: str
    span: tuple[int, int]
    claim_id: str | None = None
    reason: str = ""
    blocked_reason: str = ""

    @property
    def mapped(self) -> bool:
        return bool(self.claim_id) and not self.blocked_reason

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_reason)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "span": list(self.span),
                "claim_id": self.claim_id, "reason": self.reason,
                "blocked_reason": self.blocked_reason}


@dataclass
class GateResult:
    """合规门结果：只有 `ok=True` 才允许对外使用。"""

    text: str
    channel: str
    findings: list[Finding] = field(default_factory=list)
    reg: ClaimsRegistry | None = field(default=None, repr=False, compare=False)

    @property
    def unmapped(self) -> list[Finding]:
        return [f for f in self.findings if not f.claim_id]

    @property
    def blocked(self) -> list[Finding]:
        return [f for f in self.findings if f.claim_id and f.blocked]

    @property
    def ok(self) -> bool:
        return not self.unmapped and not self.blocked

    @property
    def claim_ids(self) -> list[str]:
        """本文案实际引用的 claim（门禁命中 + 文案归属），供发布记录追溯（任务 7）。"""
        seen: list[str] = []
        for f in self.findings:
            if f.claim_id and f.claim_id not in seen:
                seen.append(f.claim_id)
        if self.reg is not None:
            for cid in _substring_claim_ids(self.text, self.reg):
                if cid not in seen:
                    seen.append(cid)
        return seen

    def message(self) -> str:
        if self.ok:
            return f"合规门通过：引用 claim {self.claim_ids or '（无）'}"
        parts: list[str] = []
        for f in self.unmapped:
            parts.append(f"『{f.text}』({f.kind}) 无法映射到已登记 claim —— {f.reason}")
        for f in self.blocked:
            parts.append(f"『{f.text}』→ {f.claim_id} 不可用 —— {f.blocked_reason}")
        return "；".join(parts) or "合规门不通过"

    def to_dict(self) -> dict:
        return {"ok": self.ok, "channel": self.channel, "claim_ids": self.claim_ids,
                "unmapped": [f.to_dict() for f in self.unmapped],
                "blocked": [f.to_dict() for f in self.blocked],
                "findings": [f.to_dict() for f in self.findings],
                "message": self.message()}


def _usable_claims(reg: ClaimsRegistry, kind: str) -> list[Claim]:
    return [c for c in reg.all() if c.kind == kind]


def _token_index(reg: ClaimsRegistry) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for c in reg.all():
        for tok in c.tokens():
            key = _norm(tok)
            if key:
                index.setdefault(key, set()).add(c.claim_id)
            canon = _canon_numeric(tok)
            if canon:
                index.setdefault(canon, set()).add(c.claim_id)
    return index


# 泛化词：单独出现时**没有资格**映射到任何 claim（"欧盟CE认证" 不是 "CNAS 认证"）
GENERIC_TOKENS: frozenset[str] = frozenset({"认证", "资质", "备案", "奖", "专利技术"})


def _map_keyword_hit(hit_norm: str, reg: ClaimsRegistry, kind: str) -> tuple[Claim | None, str]:
    """把一处关键词命中映射到唯一 claim：先精确相等，再长词包含，仍冲突则交人工。"""
    if hit_norm in GENERIC_TOKENS:
        return None, f"『{hit_norm}』是泛化表述，未指明具体证书/资质，无法映射到已登记 claim"
    exact: set[str] = set()
    contains: dict[int, set[str]] = {}
    for c in _usable_claims(reg, kind):
        for tok in c.tokens():
            key = _norm(tok)
            if not key:
                continue
            if key == hit_norm:
                exact.add(c.claim_id)
            elif hit_norm and hit_norm in key:
                contains.setdefault(len(key), set()).add(c.claim_id)
    if len(exact) == 1:
        return reg.get(next(iter(exact))), ""
    if len(exact) > 1:
        return None, f"{kind} 关键词『{hit_norm}』精确命中多个 claim {sorted(exact)}，需人工指定"
    for length in sorted(contains, reverse=True):
        ids = contains[length]
        if len(ids) == 1:
            return reg.get(next(iter(ids))), ""
        return None, f"{kind} 关键词『{hit_norm}』命中多个 claim {sorted(ids)}，需人工指定"
    return None, ""


def _absorb_host(span: tuple[int, int], kind: str, findings: list[Finding],
                 max_gap: int = 1) -> int | None:
    """泛化词（"认证"）紧邻同 kind 的具体命中时返回其下标，供调用方合并。

    "CNAS认证" 会被正则拆成 "CNAS" + "认证" 两处命中；后者是泛化词，单独看无法映射，
    但它显然属于前者。没有这一步，正确文案会因为一个拆出来的泛化词被判"未登记"。
    """
    best: tuple[int, int] | None = None            # (gap, index)
    for i, f in enumerate(findings):
        if f.kind != kind or not f.claim_id:
            continue
        gap = min(abs(f.span[0] - span[1]), abs(span[0] - f.span[1]))
        if gap <= max_gap and (best is None or gap < best[0]):
            best = (gap, i)
    return best[1] if best else None


def scan(text: str, reg: ClaimsRegistry | None = None) -> list[Finding]:
    """扫描文本里所有需要 claim 背书的表述（不含可用性判定）。"""
    reg = reg or load()
    raw = str(text or "")
    norm = _norm(raw)
    findings: list[Finding] = []
    taken: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in taken)

    # 1) 禁用改写：命中已登记 claim 的 forbidden_rewrites（冲突参数的典型形态）
    for c in reg.all():
        for bad in c.forbidden_rewrites:
            key = _norm(bad)
            if not key:
                continue
            at = norm.find(key)
            if at >= 0:
                findings.append(Finding("forbidden_rewrite", str(bad), (at, at + len(key)),
                                        claim_id=c.claim_id,
                                        reason=f"是 {c.claim_id}（{c.display_text}）的禁用改写"))
                taken.append((at, at + len(key)))

    # 2) 数值表述：必须精确落在某条 claim 的数值口径上
    for m in _NUMERIC_RE.finditer(norm):
        span = (m.start(), m.end())
        if overlaps(*span):
            continue
        token = m.group(0)
        index = _token_index(reg)
        ids = index.get(_norm(token), set())
        canon = _canon_numeric(token)
        if not ids and canon:            # 单位/数字写法等价（"十三点八公斤" ≈ "13.8kg"）
            ids = index.get(canon, set())
        if len(ids) == 1:
            findings.append(Finding("numeric", token, span, claim_id=next(iter(ids)),
                                    reason="已登记数值口径"))
        elif len(ids) > 1:
            findings.append(Finding("numeric", token, span, claim_id=None,
                                    reason=f"命中多个 claim {sorted(ids)}，需人工指定"))
        else:
            findings.append(Finding("numeric", token, span, claim_id=None,
                                    reason="未登记数值参数（禁止自动对外使用）"))
        taken.append(span)

    # 3) 认证/质保/疗效/绝对化表述
    for kind, pattern in GROUP_PATTERNS:
        for m in pattern.finditer(norm):
            span = (m.start(), m.end())
            if overlaps(*span):
                continue
            token = m.group(0)
            claim, why = _map_keyword_hit(_norm(token), reg, kind)
            claim_id = claim.claim_id if claim else None
            if claim_id is None and _norm(token) in GENERIC_TOKENS:
                host = _absorb_host(span, kind, findings)
                if host is not None:   # 泛化词并入相邻具体关键词（"CNAS认证" 里的 "认证"）
                    findings[host] = replace(
                        findings[host],
                        span=(min(findings[host].span[0], span[0]),
                              max(findings[host].span[1], span[1])))
                    taken.append(span)
                    continue
            if claim is None and not why:
                why = f"未登记的 {kind} 类表述（禁止自动生成）"
            findings.append(Finding(kind, token, span, claim_id=claim_id,
                                    reason=why or f"映射到 {claim_id or ''}"))
            taken.append(span)
    return findings


def gate(text: str, channel: str = "", reg: ClaimsRegistry | None = None,
         on: _dt.date | None = None) -> GateResult:
    """合规门：数值/认证/质保/疗效/绝对化表述必须映射到**可用**的 claim。"""
    reg = reg or load()
    findings = scan(text, reg)
    resolved: list[Finding] = []
    for f in findings:
        if f.kind == "forbidden_rewrite":
            resolved.append(Finding(f.kind, f.text, f.span, f.claim_id, f.reason,
                                    f"禁用改写，等同伪造参数 —— {f.reason}"))
            continue
        claim = reg.get(f.claim_id) if f.claim_id else None
        reason = f.blocked_reason
        if claim is not None and not reason and not claim.usable(channel, on):
            reason = claim.block_reason(channel, on)
        resolved.append(Finding(f.kind, f.text, f.span, f.claim_id, f.reason, reason))
    return GateResult(text=str(text or ""), channel=channel, findings=resolved, reg=reg)


_SEG_SPLIT = re.compile(r"[，,。.、；;！!？?：:（）()\[\]【】\s/|]+")


def _blob_segments(blob: str) -> list[str]:
    """按标点把口径文案切成句段（"刹车灯自动亮，跟车的人一眼就看见" → 两段）。"""
    return [seg for seg in _SEG_SPLIT.split(_norm(blob)) if len(seg) >= 5]


def _substring_claim_ids(text: str, reg: ClaimsRegistry) -> list[str]:
    """② 文案与某条 claim 的 display/spoken 文案（或其中一整句）重合时归属到该 claim。"""
    norm = _norm(text)
    if len(norm) < 5:
        return []
    matches: list[tuple[int, str]] = []
    for c in reg.all():
        for blob in (c.spoken_text, c.display_text):
            key = _norm(blob)
            if len(key) >= 5 and (key in norm or norm in key):
                matches.append((len(key), c.claim_id))
                break
            hit = max((s for s in _blob_segments(blob) if s in norm), key=len, default="")
            if hit:
                matches.append((len(hit), c.claim_id))
                break
    return [cid for _, cid in sorted(matches, key=lambda m: -m[0])]


def claim_ids_in(text: str, reg: ClaimsRegistry | None = None) -> list[str]:
    """文本实际引用的 claim_id 列表（发布 artifact 用，任务 7）。

    两类来源：① 合规门命中的（数值/认证/质保/疗效/绝对化，强制口径）；
    ② 文案与某条 claim 的 display/spoken 文案互为子串的（feature 类，用于归属记录）。
    注意：② 只用于"记录引用了哪些 claim"，不放松 ① 的门禁。
    """
    reg = reg or load()
    seen: list[str] = []
    for f in scan(text, reg):
        if f.claim_id and f.claim_id not in seen:
            seen.append(f.claim_id)
    for cid in _substring_claim_ids(text, reg):
        if cid not in seen:
            seen.append(cid)
    return seen


# ── 影响面分析（任务 8：口径变更时知道哪些模板/内容受影响）──────────────
DEFAULT_IMPACT_ROOTS: tuple[str, ...] = ("lib", "s4_generate", "s5_compose", "s6_publish",
                                        "tools", "webui", "docs", "assets/products")
SKIP_DIRS = {"_deprecated_20260925", "logs", ".venv", ".git", ".pytest_cache", ".ruff_cache",
             "out", "state", "__pycache__"}
IMPACT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".mjs", ".js", ".csv"}
MAX_FILE_BYTES = 2_000_000


def _iter_source_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMPACT_SUFFIXES:
                continue
            if SKIP_DIRS & set(p.parts):
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def impact(claim_id: str, *, roots: Iterable[Path | str] | None = None,
           reg: ClaimsRegistry | None = None, max_hits: int = 200) -> list[dict]:
    """哪些文件/行引用了这条 claim 的口径（含禁用改写，便于一并排查）。"""
    reg = reg or load()
    claim = reg.get(claim_id)
    if claim is None:
        raise KeyError(f"未登记的 claim_id：{claim_id}")
    needles = [_norm(claim.claim_id)] if _norm(claim.claim_id) else []
    needles += [_norm(t) for t in claim.tokens() if _norm(t)]
    needles += [_norm(b) for b in claim.forbidden_rewrites if _norm(b)]
    labels = {_norm(t): t for t in [claim.claim_id, *claim.tokens(),
                                    *claim.forbidden_rewrites] if _norm(t)}
    roots = [Path(r) if not isinstance(r, Path) else r for r in (roots or DEFAULT_IMPACT_ROOTS)]
    roots = [(r if r.is_absolute() else ROOT / r) for r in roots]
    hits: list[dict] = []
    for path in _iter_source_files(roots):
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            low = _norm(line)
            for needle in needles:
                if needle and needle in low:
                    hits.append({"file": str(path.relative_to(ROOT)).replace("\\", "/"),
                                 "line": n, "token": labels.get(needle, needle),
                                 "text": line.strip()[:200]})
                    break
            if len(hits) >= max_hits:
                return hits
    return hits


def impact_summary(claim_id: str, **kwargs) -> dict:
    """影响面汇总：文件数、命中行数、按文件分组。"""
    hits = impact(claim_id, **kwargs)
    by_file: dict[str, int] = {}
    for h in hits:
        by_file[h["file"]] = by_file.get(h["file"], 0) + 1
    return {"claim_id": claim_id, "files": len(by_file), "hits": len(hits),
            "by_file": dict(sorted(by_file.items()))}


# ── CLI：自检 / 列出 / 影响面 ────────────────────────────────
def _main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Claims Registry 工具")
    parser.add_argument("--check", action="store_true", help="校验 claims.yaml")
    parser.add_argument("--list", action="store_true", help="列出全部 claim")
    parser.add_argument("--facts", choices=CHANNELS, help="导出某渠道可用事实块")
    parser.add_argument("--gate", help="对一段文本跑合规门")
    parser.add_argument("--channel", default="", choices=[""] + list(CHANNELS))
    parser.add_argument("--impact", help="某条 claim 的影响面")
    args = parser.parse_args(argv)

    reg = load()
    if args.check:
        print(f"claims={len(reg)} status={reg.status_counts()} digest={reg.digest()[:16]}")
        print("needs_verification:")
        print(reg.blocked_block() or "  （无）")
        return 0
    if args.list:
        for c in reg.all():
            print(f"{c.claim_id:<22} {c.status:<19} {c.kind:<13} {c.display_text}")
        return 0
    if args.facts:
        print(reg.facts_block(args.facts) or "（该渠道没有可用事实）")
        return 0
    if args.gate:
        res = gate(args.gate, args.channel)
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=1))
        return 0 if res.ok else 1
    if args.impact:
        print(json.dumps(impact_summary(args.impact), ensure_ascii=False, indent=1))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
