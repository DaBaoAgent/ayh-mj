"""模板引擎 — 10 套模板轮换 + 热点绑定 + 输出标准分镜

流程：
  1. load_templates()   → 10 套模板（YAML）
  2. pick_template()    → 按历史轮换选一套（最近用过的排除）
  3. adapt_lines()      → 先消化创意研究简报，再生成并校验台词（失败停止，不复用标准版）
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
    """轮换（宝哥规则 2026-09-24：每条视频都要有新意，不能重复用过的套路）

    1) 从未用过的模板优先——只要还有没用过的模板，就不复用旧的
    2) 全套都用过 → 才退回"避开最近 N 套"
    """
    templates = load_templates()
    if not templates:
        raise RuntimeError("没有可用模板")
    hist = _history()
    used_ids = set(hist.get("used") or hist.get("recent", []))
    recent = set(hist.get("recent", [])[-exclude_recent:])
    fresh = [t for t in templates if t["id"] not in used_ids]
    if fresh:
        return fresh[0]
    for t in templates:
        if t["id"] not in recent:
            return t
    return templates[0]


def mark_used(template_id: str) -> None:
    hist = _history()
    recent = hist.get("recent", [])
    recent.append(template_id)
    hist["recent"] = recent[-30:]
    # 全历史使用集（保新意判定的依据；首次运行时从 recent 回填 T01-T04）
    used = hist.setdefault("used", sorted(set(hist["recent"])))
    if template_id not in used:
        used.append(template_id)
    _save_history(hist)


ADAPT_SYSTEM = """你是短剧导演兼创意策划。先研读热点、爆款案例、短剧结构、同行与跨赛道对标，再用模板镜头拍出一个新故事。
你的任务：在【不改镜头数、不改单镜字数上限、不改角色关系】的前提下，重新设计开场钩子、节拍、反转和自然对白。知识库只借鉴结构，不照搬原桥段。

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
- **必须遵循 research_brief 中的短剧结构、爆款与对标参考**：
  · 前3秒开场有冲突/悬念钩子；单句台词尽量 8-12 字
  · 每2-4秒有新信息或动作，节奏明快；反转可以是惊喜/误解澄清/身份/玩法，不要总是质疑→打脸
  · 台词必须能一口气自然说出，人物接话有因果，拒绝解释性长句
  · 禁止与已用创意清单重复的桥段/梗
- **最后一镜台词必须包含品牌"爱优护轻便侠"**（CTA 硬要求；在单镜字数上限内压缩表达，不能拆出额外镜头）
- 如果某条热点不适用，要换研究简报里的相关话题来化用；绝不能照搬模板标准台词
- **场景微调（可选字段）**：若某镜台词涉及的动作/地点无法用现有 scene 表达，可输出 `scene_tweaks` 微调
  （例：主打"手机遥控"但场景是"拎车甩开"→改成"掏出手机轻按，新车自动滑到脚边"；
  或按本期思路**更换场景地点/背景**，如"机场候机楼门口/地铁站口/公园"）——
  只改动作细节与地点背景（start_state/end_state），**不改人数/机位/景别/情绪基调**；不需要就省略
- 输出 JSON 可含：`"scene_tweaks": {"2": {"start_state": "…", "end_state": "…"}}`（只列需要改的镜）

返回 JSON：{"creative_design": {"hook": "前三秒具体钩子", "beat": "每镜节拍概述", "twist": "新反转", "novelty": "与历史套路具体有何不同", "reference_use": "如何化用热点/爆款/短剧/对标"}, "lines": {"1": "第1镜台词", "2": "...", ...}, "scene_tweaks": {}, "reason": "改写说明一句话"}"""

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


def _correction(last_err: str, template: dict) -> str:
    """把上一轮的失败原因变成下一轮的明确修正指令（盲重试会让模型犯同样的错）"""
    budget = "、".join(f"镜{s['seq']}≤{int(float(s['duration']) * 4.5)}字" for s in template["shots"])
    head = f"【上一轮未通过，本轮必须修正】{last_err}\n"
    if "超字数" in last_err:
        return head + (
            f"硬性要求：每镜台词必须压进各自上限（{budget}）。"
            "超了就删字——去掉修饰词和虚词、换更短的口语词（如「非常轻」→「贼轻」），"
            "不许改故事框架、不许改角色关系、不许丢信息点。"
            "输出前逐镜数字数（标点也算），确认没超再输出。")
    if "缺镜" in last_err:
        return head + f"硬性要求：每一镜都要给台词（{budget}），一镜都不能少。"
    if "CTA" in last_err:
        return head + "硬性要求：最后一镜台词必须含「爱优护」三个字（品牌 CTA），且不超该镜字数上限。"
    if "创意设计" in last_err:
        return head + ("硬性要求：creative_design 的 hook/beat/twist/novelty/reference_use 五个字段"
                       "都要写具体内容，不能留空。")
    return head + ("硬性要求：上一轮被判与旧作品雷同。必须换一套全新的开场钩子和故事走向，"
                   "禁止照抄模板标准版台词；对照已用清单，避开所有出现过的钩子与台词。")


def adapt_lines(template: dict, hotspot_text: str, hotspot_title: str = "",
                research_brief: dict | None = None) -> dict:
    """研究驱动的模板改编；质检失败即停，避免重复标准版被送去出片。"""
    std = {str(s["seq"]): s["narration"] for s in template["shots"]}
    if not research_brief:
        from lib.creative_research import build_research_brief
        research_brief = build_research_brief()
    hotspot_text = hotspot_text or research_brief["hotspot"]["title"]

    payload = {
        "template": template["name"],
        "hot_topic": hotspot_title or hotspot_text[:60],
        "hot_context": hotspot_text[:400],
        "product_points": _product_points(),
        "research_brief": research_brief,
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
    # 叙事思路轮换（宝哥规则：每次都要不同的思路——禁止"旧车换新"反复用）
    from lib.angles import angles_block, next_angle
    ang = next_angle()
    payload["本期叙事思路（必须用这个全新框架重写故事，禁止再用'劝换车/旧车新车对比'套路）"] = (
        f"{ang['name']}：{ang['dir']}")
    ab = angles_block()
    if ab:
        payload["已用思路（禁止再用）"] = ab
    last_err = ""
    feedback = ""
    for attempt in range(1, 4):
        try:
            from lib.ideas import ideas_block, novelty_issue
            user_msg = "模板与热点：\n" + json.dumps(payload, ensure_ascii=False, indent=1)
            if feedback:
                user_msg += "\n\n" + feedback
            ib = ideas_block()
            if ib:
                user_msg += "\n\n" + ib
            out = chat_json([
                {"role": "system", "content": ADAPT_SYSTEM},
                {"role": "user", "content": user_msg},
            ], temperature=0.75, max_tokens=8000, retries=1)
            lines = out.get("lines", {})
            design = out.get("creative_design") or {}
            # 校验：字数上限
            ok = True
            for s in template["shots"]:
                seq = str(s["seq"])
                if not isinstance(lines.get(seq), str) or not lines[seq].strip():
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
                required = ("hook", "beat", "twist", "novelty", "reference_use")
                if not isinstance(design, dict) or any(not str(design.get(k) or "").strip() for k in required):
                    ok = False
                    last_err = "缺创意设计或知识库化用说明"
            if ok:
                last_err = novelty_issue(lines, std)
                ok = not last_err
            if ok:
                if attempt > 1:
                    print(f"  [OK] 台词改写第{attempt}次成功", flush=True)
                return {"lines": lines, "reason": out.get("reason", "热点已融入"),
                        "sales_point": pt, "scene_tweaks": out.get("scene_tweaks", {}) or {},
                        "angle": ang, "creative_design": design}
            print(f"  [WARN] 台词改写校验未过（{last_err}），重试 {attempt}/3", flush=True)
            feedback = _correction(last_err, template)
        except Exception as e:
            last_err = str(e)[:80]
            print(f"  [WARN] 台词改写异常（{last_err}），重试 {attempt}/3", flush=True)
            feedback = f"【上一轮调用异常】{last_err}\n请严格按系统提示的输出格式，只返回一个 JSON 对象。"
    raise RuntimeError(f"创意台词质检未通过，已停止本条视频（不回退标准版）：{last_err}")


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
