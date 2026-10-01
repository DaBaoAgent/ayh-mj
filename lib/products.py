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

# vNext StorySpec 的场景-卖点兼容表。它延续 9/26 TEMPLATE_FIT 的原则：
# 先限定“这个故事能自然讲什么”，再在兼容卖点里做保新/评分，绝不全池乱配。
STRUCTURE_FIT: dict[str, tuple[str, ...]] = {
    "S_duo_conflict": ("auto_stop", "anti_flip", "remote_15m", "joystick_360", "light_13.8"),
    "S_solo_vlog": ("light_13.8", "small_boot", "range_39", "cushion_comfy", "recline_145"),
    "S_street_interview": ("light_13.8", "fold_1s", "small_boot", "remote_15m", "joystick_360"),
    "S_suspense_reveal": ("fold_1s", "small_boot", "light_13.8", "remote_15m", "recline_145"),
    "S_magic_loop": ("fold_1s", "remote_15m", "joystick_360", "light_13.8"),
    "S_product_test": ("auto_stop", "anti_flip", "shock_18", "range_39", "light_13.8", "load_100"),
    "S_pov_first": ("auto_stop", "joystick_360", "remote_15m", "shock_18", "cushion_comfy"),
    "S_silent_slapstick": ("fold_1s", "light_13.8", "small_boot"),
    "S_emotional_story": ("cushion_comfy", "recline_145", "shock_18", "light_13.8", "range_39", "auto_stop"),
    "S_comment_reply": tuple(pid for pid, _ in _POINT_NAMES),
}

# 只有当选题本身谈到相应问题时，强语义卖点才可获得高分。
# 尤其“售后/质保”不能因为使用次数少就硬塞进敬礼、亲情、圆梦等故事。
HUMAN_STORY_TERMS: tuple[str, ...] = (
    "老兵", "敬礼", "升旗", "天安门", "纪念", "圆梦", "遗愿", "父亲", "母亲", "爷爷", "奶奶",
    "陪伴", "亲情", "一家人", "重逢", "生日愿望",
)
HUMAN_STORY_POINTS: frozenset[str] = frozenset({
    "light_13.8", "cushion_comfy", "recline_145", "shock_18", "range_39",
})

POINT_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "warranty_life": ("售后", "质保", "保修", "维修", "坏了", "故障", "服务保障"),
    "fold_1s": ("折叠", "收纳", "放车", "后备箱", "搬车"),
    "small_boot": ("后备箱", "收纳", "空间", "出门", "旅行"),
    "plane_ok": ("飞机", "高铁", "旅行", "托运", "机场"),
    "remote_15m": ("遥控", "推车", "接送", "远程"),
    "recline_145": ("休息", "午睡", "久坐", "躺", "累"),
    "shock_18": ("颠", "路面", "石子", "过坎", "减震"),
    "range_39": ("续航", "远行", "里程", "充电", "一整天"),
    "light_13.8": ("轻", "搬", "提", "出门", "陪伴", "圆梦", "老人", "老兵", "敬礼", "爷爷", "父亲"),
    "cushion_comfy": ("久坐", "舒服", "舒适", "老人", "老兵", "敬礼", "爷爷", "父亲", "陪伴"),
    "auto_stop": ("刹车", "坡", "安全", "停", "老人"),
    "anti_flip": ("坡", "翻", "安全", "上坡", "下坡"),
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


def sales_point_fit(point_id: str, *, topic: str = "", structure_id: str = "",
                    genre_id: str = "", visual_motif: str = "") -> tuple[float, list[str]]:
    """返回卖点对当前选题/骨架的语义适配度（0..1）和理由。

    这是 9/26 `TEMPLATE_FIT` 的 vNext 版本：结构匹配是基础，选题语义再加/减分。
    强语义卖点（质保、飞机、续航等）没有对应上下文时必须低分，不能靠“少用过”入选。
    """
    pid = str(point_id or "")
    text = " ".join((str(topic or ""), str(visual_motif or ""))).lower()
    fit_ids = STRUCTURE_FIT.get(str(structure_id or ""), ())
    structure_score = 1.0 if pid in fit_ids else 0.25
    reasons = ["骨架匹配" if pid in fit_ids else "骨架不匹配"]

    terms = POINT_TOPIC_TERMS.get(pid, ())
    matched = [term for term in terms if term.lower() in text]
    if matched:
        topic_score = min(1.0, 0.72 + 0.09 * len(matched))
        reasons.append("选题命中：" + "、".join(matched[:4]))
    elif terms:
        # 有明确适用语境却完全未命中：只能作为弱备选。质保尤其严格。
        topic_score = 0.05 if pid == "warranty_life" else 0.32
        reasons.append("选题未出现该卖点的适用语境")
    else:
        topic_score = 0.50
        reasons.append("通用卖点，无专属关键词")

    # 情感/人物故事中，纯售后承诺若没有售后语境直接判不适配。
    if genre_id == "G5" and pid == "warranty_life" and not matched:
        topic_score = 0.0
        reasons.append("情感故事禁止无缘由硬转售后")
    score = max(0.0, min(1.0, 0.58 * structure_score + 0.42 * topic_score))
    return round(score, 4), reasons


def compatible_points(*, topic: str, structure_id: str, genre_id: str = "",
                      visual_motif: str = "", min_score: float = 0.48) -> list[dict]:
    """按语义适配度返回可用卖点；没有合格项时宁可退回结构兼容池，也不全池乱配。"""
    used = _used()
    human_story = any(term in str(topic or "") for term in HUMAN_STORY_TERMS)
    rows: list[tuple[float, int, dict]] = []
    for point in SALES_POINTS:
        if not point.get("usable"):
            continue
        if human_story and point["id"] not in HUMAN_STORY_POINTS:
            continue
        score, _ = sales_point_fit(point["id"], topic=topic, structure_id=structure_id,
                                   genre_id=genre_id, visual_motif=visual_motif)
        if score >= min_score:
            rows.append((score, len(used.get(point["id"], [])), point))
    if not rows:
        allowed = set(STRUCTURE_FIT.get(structure_id, ()))
        if human_story:
            allowed &= set(HUMAN_STORY_POINTS)
        rows = [(0.5, len(used.get(p["id"], [])), p) for p in SALES_POINTS
                if p.get("usable") and p["id"] in allowed]
    rows.sort(key=lambda row: (-row[0], row[1], row[2]["id"]))
    return [dict(point, semantic_fit=score) for score, _, point in rows]


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
