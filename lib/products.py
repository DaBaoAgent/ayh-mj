"""产品卖点库 — 卖点池 + 卖点轮换（每条视频换主打）。

Phase 6：本文件**不再持有任何参数口径**。每个卖点的对外文案（`hook`）都实时来自
`assets/products/claims.yaml`（经 Claims Service）。参数只在 Claims Registry 里存在一份，
这里只保留"池成员 + 轮换状态 + 模板适配"这三件不属于事实层的事。
"""
import json
from pathlib import Path

from . import STATE_DIR
from . import claims as claims_mod

ROOT = Path(__file__).resolve().parent.parent
POINTS_DIR = ROOT / "assets" / "products"
STATE = STATE_DIR / "sales_points_used.json"

# ── 卖点池（每条视频轮换主打——宝哥规则 2026-09-23）──
# (point_id, 展示名, 对应的 claim_id 列表)。文案一律从 registry 取，本表不写参数。
_POINT_NAMES: list[tuple[str, str]] = [
    ("auto_stop", "松手即停"),
    ("anti_flip", "防翻系统"),
    ("fold_1s", "一键折叠"),
    ("small_boot", "折叠小巧"),
    ("plane_ok", "能上飞机高铁"),
    ("remote_15m", "手机遥控"),
    ("recline_145", "可后躺"),
    ("shock_18", "减震系统"),
    ("brake_light", "刹车自动亮灯"),
    ("range_39", "长续航"),
    ("light_13.8", "轻便可提"),
    ("cushion_comfy", "加厚坐垫"),
    ("tire_puncture", "防扎防爆胎"),
    ("lithium_safe", "锂电充电安全"),
    ("voice_ai", "AI语音播报"),
    ("joystick_360", "灵活操纵杆"),
    ("lcd_screen", "液晶屏显示"),
    ("speed_6", "多档调速"),
    ("load_100", "大承重"),
    ("warranty_life", "售后保障"),
]

# 卖点 id → 支撑它的 claim（一个卖点可以由多条 claim 组成，如质保=车架 + 电机）
POINT_CLAIMS: dict[str, tuple[str, ...]] = {
    "warranty_life": ("warranty_frame_life", "warranty_motor_2y"),
    "small_boot": ("small_boot",),
    "plane_ok": ("plane_ok",),
}


def _claim_ids(point_id: str) -> tuple[str, ...]:
    pid = str(point_id or "").strip()
    if not pid:
        return ()
    return POINT_CLAIMS.get(pid, (pid,))


def _build_points() -> list[dict]:
    """从 Claims Registry 物化卖点池；registry 不可用时只保留 id/name 且标记不可用。"""
    try:
        reg = claims_mod.load()
        broken = ""
    except Exception as exc:                       # 注册表缺失/损坏 → 一律按"不可用"
        reg, broken = None, f"{type(exc).__name__}: {exc}"
    out: list[dict] = []
    for pid, name in _POINT_NAMES:
        ids = _claim_ids(pid)
        points = [reg.get(cid) for cid in ids] if reg else []
        usable = bool(reg) and all(p is not None and p.usable("script") for p in points)
        primary = points[0] if points and points[0] is not None else None
        out.append({"id": pid, "name": name,
                    "hook": (primary.display_text if usable and primary else ""),
                    "claim_ids": list(ids), "usable": usable,
                    "blocked": "" if usable else (broken or "claim 待核验/禁止使用")})
    return out


SALES_POINTS: list[dict] = _build_points()
POINT_IDS: tuple[str, ...] = tuple(p["id"] for p in SALES_POINTS)

# ── 模板-卖点适配（防止"折叠场景讲刹车"这类画面/台词违和——宝哥规则延伸）──
TEMPLATE_FIT = {
    "T01": ["auto_stop", "anti_flip", "light_13.8", "range_39"],          # 换车对比（安全/轻/续航）
    "T02": ["fold_1s", "small_boot", "light_13.8"],                        # 折叠循环+后备箱
    "T03": ["remote_15m", "recline_145", "light_13.8"],                    # 大爷操控反差（遥控/躺）
    "T04": ["fold_1s", "small_boot", "remote_15m"],                        # 路人疑惑（折叠/遥控）
    "T05": ["auto_stop", "brake_light", "anti_flip"],                      # 安全向
    "T06": ["recline_145", "shock_18", "range_39"],                        # 舒适向
    "T07": ["remote_15m", "plane_ok", "range_39"],                         # 智能/出行
    "T08": ["plane_ok", "small_boot", "fold_1s"],                          # 出行场景
    "T09": ["shock_18", "recline_145", "brake_light"],                     # 舒适细节
    "T10": ["auto_stop", "anti_flip", "plane_ok"],                         # 安全/认证
}


def _used() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def claim_ids_for(point_id: str) -> list[str]:
    """该卖点对应的 claim_id 列表（供 artifact/发布记录，Phase 6 任务 7）。"""
    return list(_claim_ids(str(point_id or "")))


def is_usable(point_id: str, channel: str = "script") -> bool:
    """该卖点能不能自动对外使用（口径已验证 + 渠道允许）。"""
    try:
        reg = claims_mod.load()
    except Exception:
        return False
    points = [reg.get(cid) for cid in _claim_ids(str(point_id or ""))]
    return bool(points) and all(p is not None and p.usable(channel) for p in points)


def point_facts(point_id: str, channel: str = "script") -> str:
    """该卖点的对外文案（唯一来源 = registry 的 display/spoken_text）。"""
    try:
        reg = claims_mod.load()
    except Exception:
        return ""
    chunks: list[str] = []
    for cid in _claim_ids(str(point_id or "")):
        c = reg.get(cid)
        if c is None or not c.usable(channel):
            continue
        chunks.append(c.spoken_text or c.display_text)
    return "；".join(chunks)


def use_counts() -> dict:
    """每个卖点的使用次数 {point_id: n}（供 Planner 当 novelty 特征，只读不改）。"""
    used = _used()
    return {p["id"]: len(used.get(p["id"], [])) for p in SALES_POINTS}


def next_point(template_id: str = "") -> dict:
    """选本期主打卖点：优先与模板动作匹配 + 使用次数最少（且口径可用）"""
    used = _used()
    fit = TEMPLATE_FIT.get(template_id)
    pool = [p for p in SALES_POINTS if (not fit or p["id"] in fit)] or SALES_POINTS
    usable = [p for p in pool if p.get("usable")] or pool
    return min(usable, key=lambda p: len(used.get(p["id"], [])))


def record_point(point_id: str, tag: str) -> None:
    """记录本片主打卖点（tag 用 job uid 或主题名）"""
    used = _used()
    lst = used.setdefault(point_id, [])
    if tag not in lst:
        lst.append(tag)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")


def points_block() -> str:
    """已用卖点清单（注入文案提示词，强制换新卖点）"""
    used = _used()
    rows = []
    for p in SALES_POINTS:
        n = len(used.get(p["id"], []))
        if n:
            rows.append(f"{p['name']}（已用{n}次，避开当主打）")
    return "；".join(rows)


def sales_points_brief(max_chars: int = 900) -> str:
    """读 Claims Registry → 可用事实摘要（供 LLM 文案/提示词引用真实参数）。

    Phase 6：不再直接读 markdown 正文——markdown 只是 claim 的 evidence 出处。
    """
    try:
        text = claims_mod.load().facts_block("script")
    except Exception as exc:
        return f"（产品事项目前不可用：{type(exc).__name__}: {exc}）"
    return text[:max_chars]


if __name__ == "__main__":
    print(sales_points_brief(400))
    print("\n下次主打:", next_point())
    print("已用:", points_block())
    print("\n口径不可用的卖点:", [p["id"] for p in SALES_POINTS if not p["usable"]])
