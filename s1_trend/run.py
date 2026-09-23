"""s1_trend 阶段入口：热榜 + 关键词搜索 + 同行对标 → 全部写入 trends 表

用法：
    python s1_trend/run.py                    # 按 config/pipeline.yaml 全量跑
    python s1_trend/run.py --keywords 电动轮椅 轮椅生活
    python s1_trend/run.py --hot-only         # 只跑热榜
    python s1_trend/run.py --competitor-only  # 只跑对标账号
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from lib import CONFIG_DIR
from lib.state import connect


def load_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "pipeline.yaml").read_text(encoding="utf-8"))


def run(keywords: list[str] = None, hot: bool = True, competitor: bool = True,
        pages: int = 3):
    """执行 s1 阶段全流程"""
    config = load_config()
    trend_cfg = config.get("trend", {})
    keywords = keywords or trend_cfg.get("keywords", [])
    pages = pages or trend_cfg.get("pages_per_keyword", 3)

    started = time.time()
    total_saved = 0

    # 1. 热榜
    if hot:
        print("\n=== 1/3 热榜 ===", flush=True)
        try:
            from s1_trend.douyin_hot import fetch_hot_words
            fetch_hot_words(top_n=8)
        except Exception as e:
            print(f"⚠ 热榜失败: {e}", flush=True)

    # 2. 关键词搜索
    if keywords:
        print(f"\n=== 2/3 关键词搜索（{len(keywords)} 个）===", flush=True)
        from s1_trend.keyword_search import search
        for kw in keywords:
            print(f"\n🔍 关键词: {kw}", flush=True)
            try:
                result = search(kw, pages=pages, sort="likes")
                total_saved += result.get("saved", 0)
            except Exception as e:
                print(f"⚠ {kw} 失败: {e}", flush=True)

    # 3. 同行对标
    if competitor:
        competitor_accounts = trend_cfg.get("competitor_accounts", [])
        if competitor_accounts:
            print(f"\n=== 3/3 同行对标（{len(competitor_accounts)} 个账号）===", flush=True)
            from s1_trend.competitor import fetch_creator_posts
            from s1_trend.keyword_search import save_trends
            for sec_uid in competitor_accounts:
                try:
                    items = fetch_creator_posts(sec_uid, limit=20)
                    total_saved += save_trends(items)
                except Exception as e:
                    print(f"⚠ {sec_uid[:20]} 失败: {e}", flush=True)
        else:
            print("\n=== 3/3 同行对标（跳过：配置里没有对标账号）===", flush=True)

    # 汇总
    elapsed = time.time() - started
    with connect() as conn:
        total_trends = conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM trends WHERE created_at >= date('now')"
        ).fetchone()[0]

    print(f"\n{'=' * 40}", flush=True)
    print(f"✓ s1_trend 完成 | 耗时 {elapsed:.0f}s", flush=True)
    print(f"  本次入库: {total_saved} 条", flush=True)
    print(f"  库内总量: {total_trends} 条（今日 +{today}）", flush=True)
    return {"saved": total_saved, "total": total_trends, "elapsed": elapsed}


def main() -> int:
    parser = argparse.ArgumentParser(description="s1_trend 热点抓取阶段")
    parser.add_argument("--keywords", nargs="*", help="关键词列表（默认读配置）")
    parser.add_argument("--pages", type=int, default=0, help="每个关键词滚动轮数")
    parser.add_argument("--hot-only", action="store_true", help="只跑热榜")
    parser.add_argument("--competitor-only", action="store_true", help="只跑对标账号")
    parser.add_argument("--keyword-only", action="store_true", help="只跑关键词搜索")
    parser.add_argument("--check-login", action="store_true", help="只检测登录态")
    args = parser.parse_args()

    if args.check_login:
        from s1_trend.browser import ensure_login
        return 0 if ensure_login() else 1

    if args.hot_only:
        run(hot=True, competitor=False, keywords=[])
        return 0
    if args.competitor_only:
        run(hot=False, competitor=True, keywords=[])
        return 0
    if args.keyword_only:
        run(hot=False, competitor=False, keywords=args.keywords)
        return 0

    run(keywords=args.keywords, pages=args.pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
