"""软广脚本生成：从匹配的热点生成 10-20 秒短视频脚本

输出结构（JSON）：
{
  "hook": "开头3秒钩子",
  "body": "主体内容",
  "cta": "结尾引导",
  "full_text": "完整口播文案",
  "product_mention": "产品提及方式"
}

用法：
    python s2_copy/gen_script.py --top 3            # 生成 top3 匹配热点的脚本
    python s2_copy/gen_script.py --trend-id 12      # 指定热点
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import STATE_DIR
from lib.llm import chat_json
from lib.state import connect, create_job, update_job

SYSTEM_PROMPT = """你是抖音爆款文案专家，为"爱优护轻便侠218电动轮椅"写软广口播脚本。

产品卖点：轻便折叠、老年代步、自动折叠、安全稳定、适合送父母

爆款逻辑（必须遵守）：
1. 前3秒强钩子（数字冲击/反常识/身份反转/情感共鸣）
2. 中间用场景讲故事（不要报参数！要画面感）
3. 软植入产品（解决痛点的方式自然带出）
4. 结尾轻引导（不硬广，"给爸妈安排上"这类）
5. 口语化，像朋友聊天，不用书面语

字数：150-250字（对应10-20秒口播，约12-15字/秒）
禁忌：医疗疗效、绝对化用语（最/第一）、价格承诺

返回严格 JSON（不要 markdown 代码块）：
{
  "hook": "前3秒钩子文案",
  "body": "主体口播文案",
  "cta": "结尾引导文案",
  "full_text": "完整口播文案（hook+body+cta连起来）",
  "product_mention": "产品以什么方式出现（一句话说明）"
}"""


def gen_script_for_trend(trend: dict) -> dict:
    """为单个热点生成脚本"""
    user_msg = f"""热点话题：{trend.get('title', '')}
点赞：{trend.get('likes', 0)}（说明这个方向有流量）
植入角度建议：{trend.get('angle', '自然场景带入')}

请写一个电动轮椅软广脚本。"""

    data = chat_json([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ], temperature=0.8, max_tokens=2500)

    # 校验字数
    full_text = data.get("full_text", "")
    data["word_count"] = len(full_text)
    if not (100 <= data["word_count"] <= 350):
        data["warning"] = f"字数 {data['word_count']} 超出建议范围（100-350）"
    return data


def generate(top: int = 3, trend_id: int = None) -> dict:
    """批量生成脚本（默认取匹配度最高的未处理热点）"""
    with connect() as conn:
        if trend_id:
            rows = conn.execute(
                "SELECT * FROM trends WHERE id = ?", (trend_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT t.* FROM trends t
                WHERE t.matched = 1 AND t.score >= 60
                  AND t.id NOT IN (SELECT trend_id FROM jobs WHERE trend_id IS NOT NULL)
                ORDER BY t.score DESC LIMIT ?
            """, (top,)).fetchall()
        trends = [dict(r) for r in rows]

    if not trends:
        print("✓ 没有可用的匹配热点（先跑 s2_copy/analyze.py）", flush=True)
        return {"generated": 0}

    print(f"📝 为 {len(trends)} 个热点生成脚本", flush=True)
    generated = 0
    results = []

    for trend in trends:
        print(f"  [{trend['id']}] {str(trend['title'])[:40]}...", flush=True)
        try:
            script = gen_script_for_trend(trend)
        except Exception as e:
            print(f"      ✗ 生成失败: {str(e)[:60]}", flush=True)
            continue

        # 建 job 并写入文案
        uid = create_job(trend_id=trend["id"])
        update_job(uid, status="copy", script=script.get("full_text", ""),
                   script_word_count=script.get("word_count", 0))
        script["uid"] = uid
        script["trend_id"] = trend["id"]
        generated += 1
        results.append(script)
        print(f"      ✓ {script['word_count']}字 job={uid}", flush=True)
        if script.get("warning"):
            print(f"      ⚠ {script['warning']}", flush=True)
        time.sleep(0.5)

    # 落盘
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generated": generated,
        "scripts": results,
    }
    (STATE_DIR / "scripts.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✓ 生成 {generated} 个脚本", flush=True)
    for s in results[:2]:
        print(f"\n  ── {s['uid']} ({s['word_count']}字) ──", flush=True)
        print(f"  钩子: {s['hook'][:60]}", flush=True)
    return {"generated": generated, "scripts": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="软广脚本生成")
    parser.add_argument("--top", type=int, default=3, help="生成数量")
    parser.add_argument("--trend-id", type=int, help="指定热点ID")
    args = parser.parse_args()

    result = generate(top=args.top, trend_id=args.trend_id)
    return 0 if result["generated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
