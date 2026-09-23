"""智能分镜：脚本 → 镜头分解（原创模式，不依赖源视频）

每个镜头产出：
  · narration: 这一镜的口播文字（用于 TTS 配音 + 字幕）
  · scene_prompt: H3 生视频用的中文提示词（≤300字，含产品+场景+动作）
  · product_ref: 引用的产品白底图（相对 assets/products/）
  · duration: 镜头时长（秒）

用法：
    python s3_storyboard/split.py --uid job_xxx       # 指定任务
    python s3_storyboard/split.py --top 3             # 批量处理待分镜任务
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import STATE_DIR
from lib.llm import chat, chat_json
from lib.state import connect, update_job, list_jobs

# 产品白底图库（用于 H3 参考图，免生图直接可用）
PRODUCT_REFS = {
    "正侧": "正侧-3-无阴影.png",
    "正侧带背包": "正侧-3-无阴影-带头枕-背包.png",
    "45度": "45度-加水杯-无阴影.png",
    "45度带头枕": "45度-加水杯-无阴影-带头枕.png",
    "折叠": "折叠-无阴影.png",
    "后躺": "后躺_Main_0045.jpg",
    "后躺老外": "后躺老外.png",
    "轻便侠5517": "轻便侠-5517x5517-无阴影.jpg",
}

SYSTEM_PROMPT = """你是短视频分镜专家。把口播脚本拆解成 4-6 个镜头，用于 AI 视频生成。

产品：爱优护轻便侠218电动轮椅（自动折叠、轻便、稳）

分镜规则：
1. 镜头1（钩子，2-3秒）：人物+场景，吸引眼球
2. 中间镜头（每镜 3-5 秒）：展示场景/痛点/使用过程
3. 至少 2 个镜头出现电动轮椅整车（产品可见）
4. 结尾镜头（2-3秒）：温馨收尾+产品
5. 每个镜头的 scene_prompt 是给 AI 视频生成模型的提示词：
   - 中文，≤150字
   - 结构：场景(地点/光线) + 主体人物动作 + 产品外观状态 + 镜头运动
   - 要求写实风格、自然光、无文字无水印
   - 人物：老年人（60-70岁），穿着得体
   - 产品外观必须与参考图一致（白底图会作为参考图传入）

参考图可选项（product_ref 字段必须从这里选）：
- "正侧" / "正侧带背包" / "45度" / "45度带头枕" / "折叠" / "后躺" / "后躺老外" / "轻便侠5517"
- 不出现轮椅的镜头用空字符串 ""

返回严格 JSON（不要 markdown 代码块）：
{
  "shots": [
    {
      "seq": 1,
      "duration": 3,
      "narration": "这一镜的口播文字",
      "scene_prompt": "AI生视频提示词（≤150字）",
      "product_ref": "折叠",
      "shot_type": "钩子/场景/产品展示/痛点/收尾"
    }
  ],
  "total_duration": 15
}"""


def split_script(script: str, trend_title: str = "") -> dict:
    """把脚本拆成分镜"""
    user_msg = f"""话题背景：{trend_title}

口播脚本：
{script}

请拆解分镜。总时长控制在 10-20 秒。"""

    result = chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ], temperature=0.5, max_tokens=3000)

    text = result.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    data = json.loads(text)

    # 校验
    shots = data.get("shots", [])
    for shot in shots:
        # 校验 product_ref 合法性
        if shot.get("product_ref") and shot["product_ref"] not in PRODUCT_REFS:
            shot["product_ref"] = ""  # 非法引用置空
        # scene_prompt 长度校验
        if len(shot.get("scene_prompt", "")) > 300:
            shot["scene_prompt"] = shot["scene_prompt"][:290] + "..."
    data["shots"] = shots
    data["shots_count"] = len(shots)
    data.setdefault("total_duration", sum(s.get("duration", 3) for s in shots))
    return data


def process_job(uid: str) -> dict:
    """处理单个任务的分解"""
    from lib.state import get_job
    job = get_job(uid)
    if not job:
        raise ValueError(f"任务不存在: {uid}")
    if not job.get("script"):
        raise ValueError(f"任务 {uid} 没有文案")

    # 取热点标题作为背景
    trend_title = ""
    if job.get("trend_id"):
        with connect() as conn:
            row = conn.execute("SELECT title FROM trends WHERE id = ?",
                               (job["trend_id"],)).fetchone()
            if row:
                trend_title = row["title"]

    print(f"  🎬 分镜: {uid}（{job.get('script_word_count', '?')}字）", flush=True)
    storyboard = split_script(job["script"], trend_title)

    update_job(uid, status="storyboard",
               storyboard=json.dumps(storyboard, ensure_ascii=False))
    print(f"      ✓ {storyboard['shots_count']} 个镜头 / {storyboard['total_duration']}秒", flush=True)
    for shot in storyboard["shots"]:
        ref = f"[{shot['product_ref']}]" if shot.get("product_ref") else "[无产品]"
        print(f"        {shot['seq']}. {shot['duration']}s {ref} {shot['narration'][:30]}", flush=True)
    return storyboard


def run(top: int = 3, uid: str = None) -> dict:
    """批量分镜"""
    if uid:
        uids = [uid]
    else:
        jobs = [j for j in list_jobs("copy", limit=top * 2) if j.get("script")]
        uids = [j["uid"] for j in jobs[:top]]

    if not uids:
        print("✓ 没有待分镜的任务（先跑 s2_copy/gen_script.py）", flush=True)
        return {"processed": 0}

    print(f"🎬 分镜 {len(uids)} 个任务", flush=True)
    processed = 0
    results = []

    for u in uids:
        try:
            sb = process_job(u)
            results.append({"uid": u, "storyboard": sb})
            processed += 1
        except Exception as e:
            print(f"      ✗ {u} 失败: {str(e)[:60]}", flush=True)
        time.sleep(0.5)

    # 落盘
    out = {
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "processed": processed,
        "results": results,
    }
    (STATE_DIR / "storyboards.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✓ 分镜完成 {processed}/{len(uids)}", flush=True)
    return {"processed": processed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="智能分镜")
    parser.add_argument("--uid", help="指定任务UID")
    parser.add_argument("--top", type=int, default=3, help="批量数量")
    args = parser.parse_args()

    result = run(top=args.top, uid=args.uid)
    return 0 if result["processed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
