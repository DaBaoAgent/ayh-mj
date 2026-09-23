"""同行对标账号作品采集（免签名，页内 fetch 作者作品接口）

用法：
    python s1_trend/competitor.py --sec-uid MS4wLj... --limit 20
    python s1_trend/competitor.py --from-config   # 从 config/pipeline.yaml 读对标账号
"""
from __future__ import annotations

import argparse
import json
import yaml
from pathlib import Path
from typing import Any

from s1_trend.browser import ctx
from lib import CONFIG_DIR

POSTS_JS = """
async (secUid) => {
  const r = await fetch(`/aweme/v1/web/aweme/post/?sec_user_id=${secUid}&count=20&max_cursor=0&aid=6383&device_platform=webapp`,
                        {credentials: 'include'});
  const t = await r.text();
  if (!t || !t.length) return {error: 'empty-body'};
  try { const j = JSON.parse(t); return {list: j.aweme_list || [], has_more: j.has_more, cursor: j.max_cursor}; }
  catch (e) { return {error: 'bad-json'}; }
}
"""


def fetch_creator_posts(sec_uid: str, limit: int = 20) -> list[dict[str, Any]]:
    """抓取某作者的作品列表（免签名，页内 fetch）"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        c = ctx(pw)
        try:
            page = c.new_page()
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            result = page.evaluate(POSTS_JS, sec_uid)
        finally:
            c.close()

    if result.get("error"):
        print(f"  ✗ 抓取失败: {result['error']}", flush=True)
        return []

    awemes = result.get("list") or []
    print(f"  获取 {len(awemes)} 条作品（has_more={result.get('has_more')}）", flush=True)

    from s1_trend.keyword_search import _aweme_to_trend
    items = []
    for aweme in awemes[:limit]:
        trend = _aweme_to_trend(aweme, f"competitor:{sec_uid[:20]}")
        items.append(trend)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="同行对标账号采集")
    parser.add_argument("--sec-uid", help="对标账号的 sec_uid")
    parser.add_argument("--limit", type=int, default=20, help="最多抓取条数")
    parser.add_argument("--from-config", action="store_true", help="从配置读账号列表")
    args = parser.parse_args()

    sec_uids = []
    if args.from_config:
        config_file = CONFIG_DIR / "pipeline.yaml"
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        sec_uids = config.get("trend", {}).get("competitor_accounts", [])
        if not sec_uids:
            print("配置里没有对标账号，请先在 config/pipeline.yaml 的 trend.competitor_accounts 添加", flush=True)
            return 1
    elif args.sec_uid:
        sec_uids = [args.sec_uid]
    else:
        parser.print_help()
        return 1

    all_items = []
    for sec_uid in sec_uids:
        print(f"📊 抓取账号: {sec_uid[:30]}...", flush=True)
        items = fetch_creator_posts(sec_uid, args.limit)
        all_items.extend(items)

    if all_items:
        from s1_trend.keyword_search import save_trends
        saved = save_trends(all_items)
        print(f"\n✓ 共 {len(all_items)} 条，入库 {saved} 条", flush=True)
        top = sorted(all_items, key=lambda x: x["likes"] or 0, reverse=True)[:5]
        for t in top:
            print(f"  ♥{t['likes']:>7}  {str(t['title'])[:46]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
