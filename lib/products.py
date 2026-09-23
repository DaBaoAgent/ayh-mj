"""产品卖点库 — 从归档的卖点文档提供文案素材 + 卖点轮换（每条视频换卖点）"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POINTS_DIR = ROOT / "assets" / "products"
STATE = ROOT / "state" / "sales_points_used.json"

# ── 卖点池（每条视频轮换主打——宝哥规则 2026-09-23）──
SALES_POINTS = [
    {"id": "auto_stop", "name": "松手即停", "hook": "电磁刹车，松手即停、坡停不溜"},
    {"id": "anti_flip", "name": "3.0防翻系统", "hook": "防前翻侧翻后翻，30度陡坡不后翻"},
    {"id": "fold_1s", "name": "1秒折叠", "hook": "镁铝合金车架，一按一压一秒折好"},
    {"id": "small_boot", "name": "比行李箱还小", "hook": "折叠后31.5cm宽，后备箱随便放"},
    {"id": "plane_ok", "name": "能上飞机高铁", "hook": "CNAS认证，上飞机免费托运"},
    {"id": "remote_15m", "name": "15米手机遥控", "hook": "手机遥控，不用弯腰推"},
    {"id": "recline_145", "name": "145度后躺", "hook": "久坐能躺平，午睡都行"},
    {"id": "shock_18", "name": "18股护脊减震", "hook": "汽车级减震，过坎不颠"},
    {"id": "brake_light", "name": "刹车自动亮灯", "hook": "高亮尾灯自动亮，防追尾"},
    {"id": "range_39", "name": "续航39公里", "hook": "充一次跑39公里"},
    {"id": "light_13.8", "name": "13.8公斤", "hook": "单手可提"},
]


def _used() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


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


def next_point(template_id: str = "") -> dict:
    """选本期主打卖点：优先与模板动作匹配 + 使用次数最少"""
    used = _used()
    fit = TEMPLATE_FIT.get(template_id)
    pool = [p for p in SALES_POINTS if (not fit or p["id"] in fit)] or SALES_POINTS
    return min(pool, key=lambda p: len(used.get(p["id"], [])))


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
    """读卖点库 → 摘要（供 LLM 文案/提示词引用真实卖点参数）"""
    p = POINTS_DIR / "轻便侠218_卖点.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    # 截取正文（跳标题行）
    return text[:max_chars]


if __name__ == "__main__":
    print(sales_points_brief(400))
    print("\n下次主打:", next_point())
    print("已用:", points_block())
