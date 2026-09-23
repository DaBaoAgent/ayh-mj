"""模板引擎 — 10 套模板轮换 + 热点绑定 + 输出标准分镜

流程：
  1. load_templates()   → 10 套模板（YAML）
  2. pick_template()    → 按历史轮换选一套（最近用过的排除）
  3. adapt_lines()      → 用 LLM 把热点话题融入台词（保持字数/结构约束；失败回退标准版）
  4. to_storyboard()    → 输出标准分镜 JSON（含每镜参考图/音色/时长）

约束（adapt_lines 强制）：
  · 每镜台词字数 ≤ duration × 4.5
  · 不改镜头数/时长/目的/景别
  · 每镜仍单人说话（画外音合并写 "S2+S1画外" 保持原样）
"""
import json
from pathlib import Path

sys_path = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(sys_path))
import yaml

from lib.llm import chat_json

TPL_DIR = sys_path / "assets" / "templates"
STATE_FILE = sys_path / "state" / "template_history.json"


def load_templates() -> list[dict]:
    """加载全部模板（part1+part2）"""
    templates: list[dict] = []
    for f in sorted(TPL_DIR.glob("video_templates_part*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        templates.extend(data.get("templates", []))
    return templates


def _history() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"recent": []}


def _save_history(h: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")


def pick_template(exclude_recent: int = 3) -> dict:
    """轮换：优先避开最近用过的 N 套"""
    templates = load_templates()
    if not templates:
        raise RuntimeError("没有可用模板")
    hist = _history()
    recent = set(hist.get("recent", [])[-exclude_recent:])
    for t in templates:
        if t["id"] not in recent:
            return t
    return templates[0]


def mark_used(template_id: str) -> None:
    hist = _history()
    recent = hist.get("recent", [])
    recent.append(template_id)
    hist["recent"] = recent[-30:]
    _save_history(hist)


ADAPT_SYSTEM = """你是短剧台词改写师。给你一套视频模板的镜头台词（标准版）和一个热点话题。
你的任务：在【不改镜头结构、不改单镜字数上限、不改角色关系】的前提下，把热点话题自然融入台词（融入开场钩子最优先）。

【角色铁律（违反=失败）】
1. 每个镜头的 speaker 标注了说话人身份——台词必须符合该身份
2. 禁止改变称呼与角色关系：儿子叫"妈"就是妈，不能把"妈"改成"爷爷"；坐车人是谁就写谁
3. 热点元素如果与模板角色冲突（如热点讲"爷爷"但模板角色是"母亲"）：
   - 优先把热点转译为通用表述（"爷爷十年旧轮椅"→"这车用了十年"/"老一辈的旧车"）
   - 或只绑定数据/事实（"十年"/"后备箱"），不要硬塞新角色
4. 人称代词（他/她/它）必须与所指角色一致
5. 改写后通读检查：每句话"谁对谁说"是否通顺合理

规则：
- 每镜台词字数必须 ≤ 该镜时长×4.5（如 3 秒 ≤ 13 字）
- **口语化（重要）**：像真人聊天一样自然——用口语词（诶/哎/咋/啥/哟/嘞/呗）、口语短句、反问语气；
  禁止书面语（"是否""非常""因此"）、禁止广告腔（"值得拥有"）；例：
  · 书面："这款轮椅非常轻便" → 口语："这车贼轻，一只手就拎起来"
  · 书面："您可以尝试折叠" → 口语："你试试，咔一下就折上了"
- 会话自然口语，保持原有对抗张力/情感
- 数字用中文读音写（218→二幺八，"一"读"幺"；13.8→十三点八）
- 不改变说话人分配
- 参考 product_points 把真实卖点自然融入（数字/功能/场景，不硬广）
- **必须遵循 drama_structure_rules（短剧结构库）创作**：
  · 前3秒开场有冲突/悬念钩子；单句台词尽量 8-12 字
  · 有质疑→打脸的反转结构；台词大白话零修饰（拒绝解释性长句）
  · 禁止与已用创意清单重复的桥段/梗
- **最后一镜台词必须包含品牌"爱优护轻便侠"**（CTA 硬要求；若超字数就把该镜拆两段：前半回应+后半品牌）
- 如果热点完全不适用，原样返回（宁可不动）
- **场景微调（可选字段）**：若某镜台词涉及的动作无法用现有 scene 表达（例：主打"手机遥控"但场景是"拎车甩开"），
  可输出 `scene_tweaks` 微调该镜动作细节（例："掏出手机轻按，新车自动滑到脚边"）——
  只改动作细节（start_state/end_state），**不改人数/机位/景别/情绪基调**；不需要就省略
- 输出 JSON 可含：`"scene_tweaks": {"2": {"start_state": "…", "end_state": "…"}}`（只列需要改的镜）

返回 JSON：{"lines": {"1": "第1镜台词", "2": "...", ...}, "reason": "改写说明一句话"}"""

# 角色引用 → 可读描述（给 LLM 理解角色关系）
_CAST_READABLE = {
    "son": "儿子(45岁男)", "son_urgent": "儿子(45岁男,急切)", "son_proud": "儿子(得意)",
    "mother": "母亲(68岁女,通常坐车人)", "mother_stubborn": "母亲(68岁女,倔强,通常坐车人)",
    "mother_softening": "母亲(68岁女,松动)", "elder": "邻居大爷(65岁男)",
    "courier": "快递员(30岁男)", "dog": "宠物狗",
    "old_wheelchair": "旧轮椅(道具)", "折叠": "折叠新轮椅(道具)", "正侧": "新轮椅(道具)", "45度": "新轮椅(道具)",
}


def _readable_role(ref: str) -> str:
    if ref in _CAST_READABLE:
        return _CAST_READABLE[ref]
    if ref.startswith("@"):
        return f"槽位{ref}(轮换演员)"
    return ref


def _product_points() -> str:
    """产品卖点摘要（供文案引用真实参数）"""
    try:
        from lib.products import sales_points_brief
        return sales_points_brief()
    except Exception:
        return ""


def _drama_rules() -> str:
    """短剧结构库摘要（爆款结构智能调用：节拍/爽点/台词规则）"""
    try:
        from lib.copybook import structure_brief
        return structure_brief()
    except Exception:
        return ""


def _bridges() -> str:
    """桥段库摘要（每日2点cron刷新：短剧桥段/同行爆款/跨赛道爆款）"""
    try:
        from lib.copybook import bridges_brief
        return bridges_brief()
    except Exception:
        return ""


def adapt_lines(template: dict, hotspot_text: str, hotspot_title: str = "") -> dict:
    """热点融入台词；失败回退标准版"""
    std = {str(s["seq"]): s["narration"] for s in template["shots"]}
    if not hotspot_text:
        return {"lines": std, "reason": "无热点，用标准版"}

    payload = {
        "template": template["name"],
        "hot_topic": hotspot_title or hotspot_text[:60],
        "hot_context": hotspot_text[:400],
        "product_points": _product_points(),
        "drama_structure_rules": _drama_rules(),
        "trend_bridges": _bridges(),
        "shots": [
            {"seq": s["seq"], "duration": s["duration"],
             "max_chars": int(int(s["duration"]) * 4.5)
             if isinstance(s["duration"], (int, float)) else int(float(s["duration"]) * 4.5),
             "speaker": s["speaker"],
             "speaker_role": " + ".join(_readable_role(r) for r in s.get("cast_refs", [])
                                        if not r.startswith("@") and r in _CAST_READABLE)
             or _readable_role(s["speaker"]),
             "scene": f"{s.get('start_state', '')} → {s.get('end_state', '')}",
             "line": s["narration"]}
            for s in template["shots"]
        ],
    }
    # 卖点轮换（宝哥规则：每条视频换一个卖点主打；与本模板动作匹配优先）
    from lib.products import next_point, points_block
    pt = next_point(template.get("id", ""))
    payload["本期主打卖点（必须围绕它设计核心冲突/台词，不要用已用过的）"] = (
        f"{pt['name']}：{pt['hook']}")
    pb = points_block()
    if pb:
        payload["卖点轮换规则"] = f"以下卖点已当过主打——本期不要再用：{pb}"
    last_err = ""
    for attempt in range(1, 4):
        try:
            from lib.ideas import ideas_block
            user_msg = "模板与热点：\n" + json.dumps(payload, ensure_ascii=False, indent=1)
            ib = ideas_block()
            if ib:
                user_msg += "\n\n" + ib
            out = chat_json([
                {"role": "system", "content": ADAPT_SYSTEM},
                {"role": "user", "content": user_msg},
            ], temperature=0.5, max_tokens=2000)
            lines = out.get("lines", {})
            # 校验：字数上限
            ok = True
            for s in template["shots"]:
                seq = str(s["seq"])
                if seq not in lines:
                    ok = False
                    last_err = f"缺镜{seq}"
                    break
                max_chars = int(float(s["duration"]) * 4.5)
                if len(lines[seq]) > max_chars:
                    ok = False
                    last_err = f"镜{seq}超字数({len(lines[seq])}>{max_chars})"
                    break
            # 校验：最后一镜必须含品牌 CTA
            if ok:
                last_seq = str(template["shots"][-1]["seq"])
                if "爱优护" not in lines.get(last_seq, ""):
                    ok = False
                    last_err = f"镜{last_seq}缺品牌CTA"
            if ok:
                if attempt > 1:
                    print(f"  ✓ 台词改写第{attempt}次成功", flush=True)
                return {"lines": lines, "reason": out.get("reason", "热点已融入"),
                        "sales_point": pt, "scene_tweaks": out.get("scene_tweaks", {}) or {}}
            print(f"  ⚠ 台词改写校验未过（{last_err}），重试 {attempt}/3", flush=True)
        except Exception as e:
            last_err = str(e)[:80]
            print(f"  ⚠ 台词改写异常（{last_err}），重试 {attempt}/3", flush=True)
    return {"lines": std, "reason": f"校验未过回退标准版({last_err})", "sales_point": pt}


def to_storyboard(template: dict, lines: dict | None = None,
                  job_uid: str = "") -> dict:
    """模板 + 台词 → 标准分镜 JSON（下游 s4_generate 直接可用）"""
    storyboard = {
        "job_uid": job_uid,
        "template_id": template["id"],
        "template_name": template["name"],
        "type": template["type"],
        "total_duration": template["duration"],
        "concept": template["concept"],
        "shots": [],
    }
    for s in template["shots"]:
        seq = str(s["seq"])
        storyboard["shots"].append({
            "seq": s["seq"],
            "duration": s["duration"],
            "purpose": s["purpose"],
            # 构图规范（2026-09-23 宝哥定）：统一大全景，人物全身占画面高度约1/2
            "shot_size": "大全景",
            "camera": s["camera"],
            "start_state": s["start_state"],
            "end_state": s["end_state"],
            "speaker": s["speaker"],
            "narration": (lines or {}).get(seq, s["narration"]),
            "narration_std": s["narration"],
            "sound_design": s["sound_design"],
            "cast_refs": s["cast_refs"],
            "product_ref": s.get("product_ref", ""),
        })
    return storyboard


if __name__ == "__main__":
    # 自检：加载 + 轮换 + 输出
    tpls = load_templates()
    print(f"✓ 加载 {len(tpls)} 套模板:")
    for t in tpls:
        n_shots = len(t["shots"])
        total = sum(float(s["duration"]) for s in t["shots"])
        print(f"  {t['id']} {t['name']:8s} [{t['type']}] {n_shots}镜/{total:.0f}s")
