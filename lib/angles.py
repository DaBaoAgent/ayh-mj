"""叙事思路库 — 每条视频换一个故事框架（不重复"旧车换新"套路）

宝哥规则 2026-09-23："不要老是旧车新车，每次都要不同的思路"
- 记录已用思路，新片从"未用池"优先取
- 思路 = 故事由头/场景背景/冲突类型（不是台词的微调）
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "story_angles_used.json"

# ── 思路池（每次不同的叙事框架）──
ANGLES = [
    # —— 已用（回填历史）——
    {"id": "A1", "name": "换车劝架", "dir": "子女劝父母把旧车换掉，感动式对抗", "used_up": True},
    {"id": "A2", "name": "魔性循环展示", "dir": "同一动作重复三次形成节奏洗脑", "used_up": True},
    {"id": "A3", "name": "大爷反差", "dir": "老人玩转新装备形成潇洒反差", "used_up": True},
    {"id": "A4", "name": "赶集节日场景", "dir": "中秋/赶集等节日由头送关怀", "used_up": True},
    {"id": "A5", "name": "路人疑惑三连", "dir": "路人质疑→实测打脸", "used_up": True},
    {"id": "A6", "name": "拆车好奇", "dir": "围观者拆解误会引发误会→澄清", "used_up": True},
    {"id": "A7", "name": "养生误区打脸", "dir": "跟热点误区唱反调，用产品打脸", "used_up": True},
    # —— 未用池（优先取）——
    {"id": "B1", "name": "机场托运", "dir": "带轮椅坐飞机去旅行——托运到登机全程（轻便/可上飞机卖点天然场景）"},
    {"id": "B2", "name": "地铁通勤", "dir": "早高峰地铁站——进电梯、过闸机、挤车厢的出行自由"},
    {"id": "B3", "name": "暴雨突袭", "dir": "突降大雨——从狼狈到淡定从容的对比（时间情绪反差）"},
    {"id": "B4", "name": "晨练竞技", "dir": "公园晨练老头老太太——轮椅版健身battle，喜剧化"},
    {"id": "B5", "name": "孝心礼物真香", "dir": "偷偷买礼物被爸妈嫌弃→用起来真香（先抑后扬）"},
    {"id": "B6", "name": "快递小哥视角", "dir": "快递/外卖员送货上门——看到轮椅的羡慕/惊讶"},
    {"id": "B7", "name": "超市满载", "dir": "超市采购装满挂满——承重与自由购物（生活流）"},
    {"id": "B8", "name": "轮椅竞速", "dir": "小区/公园趣味竞速——老人版速度与激情（夸张喜剧）"},
    {"id": "B9", "name": "维修店报废对比", "dir": "维修店老板劝别修了——新旧对比的专业视角（第三方背书）"},
    {"id": "B10", "name": "婚礼出席", "dir": "穿正装出席晚辈婚礼——体面出行（情感仪式感）"},
    {"id": "B11", "name": "景点打卡", "dir": "旅游景点全程自己走——年轻人跟不上的反转"},
    {"id": "B12", "name": "遛狗互动", "dir": "遛狗时狗拉轮椅/狗坐车——萌宠吸睛+轻松搞笑"},
    {"id": "B13", "name": "露营野餐", "dir": "全家露营——轮椅进草地土路不费劲（场景拓展）"},
    {"id": "B14", "name": "菜市场砍价", "dir": "菜市场日常——老板熟客关系+灵活穿行（烟火气）"},
    {"id": "B15", "name": "演唱会排队", "dir": "陪爸妈追星/看戏排队——活力老年生活（反差萌）"},
]


def _used() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def next_angle() -> dict:
    """选本期叙事思路：只用未使用框架，耗尽时停止而非重复旧套路。"""
    used = _used()
    pool = [a for a in ANGLES if not a.get("used_up")]
    fresh = [a for a in pool if not used.get(a["id"])]
    if not fresh:
        raise RuntimeError("未使用的叙事思路已耗尽；请扩充思路库，不能重复旧套路")
    return fresh[0]


def record_angle(angle_id: str, tag: str) -> None:
    used = _used()
    lst = used.setdefault(angle_id, [])
    if tag not in lst:
        lst.append(tag)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")


def angles_block() -> str:
    """已用思路清单（注入提示词强制避开）"""
    used = _used()
    names = []
    for a in ANGLES:
        if a.get("used_up") or used.get(a["id"]):
            names.append(a["name"])
    return "、".join(names)


if __name__ == "__main__":
    print("下次思路:", next_angle())
    print("已用:", angles_block())
