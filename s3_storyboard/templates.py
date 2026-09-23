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
import re
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
你的任务：在【不改镜头结构、不改单镜字数上限】的前提下，把热点话题自然融入台词（融入开场钩子最优先）。

规则：
1. 每镜台词字数必须 ≤ 该镜时长×4.5（如 3 秒 ≤ 13 字）
2. 如果热点与产品/家庭场景弱相关，只微调开场钩子句（第 1 镜），其余保持原样
3. 如果热点完全不适用，原样返回（宁可不动）
4. 台词保持口语、有对抗张力（如原句有）
5. 数字仍用中文（218→二一八）
6. 不改变说话人分配

返回 JSON：{"lines": {"1": "第1镜台词", "2": "...", ...}, "reason": "改写说明一句话"}"""


def adapt_lines(template: dict, hotspot_text: str, hotspot_title: str = "") -> dict:
    """热点融入台词；失败回退标准版"""
    std = {str(s["seq"]): s["narration"] for s in template["shots"]}
    if not hotspot_text:
        return {"lines": std, "reason": "无热点，用标准版"}

    payload = {
        "template": template["name"],
        "hot_topic": hotspot_title or hotspot_text[:60],
        "hot_context": hotspot_text[:400],
        "shots": [
            {"seq": s["seq"], "duration": s["duration"],
             "max_chars": int(int(s["duration"]) * 4.5)
             if isinstance(s["duration"], (int, float)) else int(float(s["duration"]) * 4.5),
             "speaker": s["speaker"], "line": s["narration"]}
            for s in template["shots"]
        ],
    }
    try:
        out = chat_json(ADAPT_SYSTEM,
                        "模板与热点：\n" + json.dumps(payload, ensure_ascii=False, indent=1))
        lines = out.get("lines", {})
        # 校验：字数上限
        ok = True
        for s in template["shots"]:
            seq = str(s["seq"])
            if seq not in lines:
                ok = False
                break
            max_chars = int(float(s["duration"]) * 4.5)
            if len(lines[seq]) > max_chars:
                ok = False
                break
        if ok:
            return {"lines": lines, "reason": out.get("reason", "热点已融入")}
    except Exception as e:
        return {"lines": std, "reason": f"改写失败回退标准版: {str(e)[:80]}"}
    return {"lines": std, "reason": "校验未过，回退标准版"}


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
            "shot_size": s["shot_size"],
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
