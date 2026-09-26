"""热点匹配分析：用 DeepSeek 判断热点能否植入电动轮椅软广

判定标准（继承 AutoAYH 产品匹配器经验）：
  · 三选一必中：场景植入 / 品类展示 / 痛点共鸣
  · 一票否决：残障倡导、医疗康复、竞品硬广、猎奇搞笑、无人出镜

用法：
    python s2_copy/analyze.py --limit 20        # 分析库内未评分热点
    python s2_copy/analyze.py --min-likes 5000  # 只分析高赞
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.llm import chat_json
from lib.state import connect

SYSTEM_PROMPT = """你是内容策略专家，判断抖音热点视频能否植入"电动轮椅"产品软广。

产品：爱优护轻便侠218电动轮椅（轻便折叠、老年代步、出行辅具）

评分标准（0-100）：
- 场景契合（0-40分）：老年人出行、旅游、就医、家庭关爱、送礼等场景
- 人群匹配（0-30分）：受众是老年人及其子女
- 植入自然度（0-30分）：产品能自然融入内容不显突兀

一票否决（score=0）：
- 残障权益倡导类（主体人群与产品人群不同，硬植入不有效）
- 医疗康复类（合规风险）
- 竞品硬广
- 猎奇搞笑类（调性不符）

返回严格 JSON（不要 markdown 代码块）：
{"score": 75, "match": true, "angle": "植入角度一句话", "reason": "判定理由一句话"}"""


def analyze_trend(trend: dict) -> dict:
    """分析单个热点"""
    user_msg = f"""标题：{trend.get('title', '')}
作者：{trend.get('author', '')}
点赞：{trend.get('likes', 0)}  评论：{trend.get('comments', 0)}  时长：{trend.get('duration', 0)}秒"""

    try:
        data = chat_json([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ], temperature=0.3, max_tokens=2000)
        return {
            "score": float(data.get("score", 0)),
            "match": bool(data.get("match", False)),
            "angle": data.get("angle", ""),
            "reason": data.get("reason", ""),
        }
    except Exception as e:
        return {"score": 0, "match": False, "angle": "", "reason": f"分析失败: {str(e)[:60]}"}


def run_analysis(limit: int = 20, min_likes: int = 0, match_only: bool = False) -> dict:
    """批量分析库内热点"""
    with connect() as conn:
        rows = conn.execute("""
            SELECT id, title, author, likes, comments, duration FROM trends
            WHERE score IS NULL AND likes >= ?
            ORDER BY likes DESC LIMIT ?
        """, (min_likes, limit)).fetchall()
        trends = [dict(r) for r in rows]

    if not trends:
        print("✓ 没有待分析的热点", flush=True)
        return {"analyzed": 0, "matched": 0}

    print(f"📊 待分析 {len(trends)} 条热点", flush=True)
    analyzed = 0
    matched = 0
    results = []

    for i, trend in enumerate(trends, 1):
        print(f"  [{i}/{len(trends)}] {str(trend['title'])[:40]}...", flush=True)
        result = analyze_trend(trend)

        # 写库
        with connect() as conn:
            conn.execute("""
                UPDATE trends SET score = ?, matched = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (result["score"], 1 if result["match"] else 0, trend["id"]))
            conn.commit()

        analyzed += 1
        if result["match"]:
            matched += 1
        results.append({**trend, **result})
        print(f"      → {result['score']:.0f}分 {'✓' if result['match'] else '✗'} {result['reason'][:40]}", flush=True)
        time.sleep(0.5)  # 温柔限速

    # 结果落盘
    out = {
        "analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "analyzed": analyzed,
        "matched": matched,
        "results": sorted(results, key=lambda x: x["score"], reverse=True),
    }
    from lib import STATE_DIR
    (STATE_DIR / "analyze_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✓ 分析完成: {analyzed} 条，匹配 {matched} 条", flush=True)
    top = out["results"][:5]
    for r in top:
        print(f"  {r['score']:.0f}分 {str(r['title'])[:36]} | {r['angle'][:30]}", flush=True)
    return {"analyzed": analyzed, "matched": matched}


def main() -> int:
    parser = argparse.ArgumentParser(description="热点匹配分析")
    parser.add_argument("--limit", type=int, default=20, help="分析条数上限")
    parser.add_argument("--min-likes", type=int, default=0, help="最低点赞数过滤")
    args = parser.parse_args()

    run_analysis(limit=args.limit, min_likes=args.min_likes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
