"""关键词搜索采集（拦截搜索页自身发的 /aweme/v1/web/search/item/ 响应）

原理（来自 AutoAYH 2026-09-22 实战）：
  · 自己签名调老接口已失效且会挂死 → 改为「拦截页面自身请求的响应」
  · 打开 https://www.douyin.com/search/<kw>?type=video，页面自己发接口，滚动自动翻页
  · 每个关键词 120s 硬上限，绝不无限等

用法：
    python s1_trend/keyword_search.py --keyword 电动轮椅 --pages 3 --sort likes
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from s1_trend.browser import ctx
from lib import STATE_DIR
from lib.state import connect

SORT_MAP = {"general": 0, "new": 1, "likes": 2, "点赞": 2, "综合": 0, "最新": 1}
SEARCH_URL = "https://www.douyin.com/search/{kw}?type=video&sort_type={st}"
HIT_MARKERS = ("/aweme/v1/web/search/item/", "/aweme/v1/web/general/search/")


def _collect_from_body(body: str) -> list[dict]:
    """从搜索响应体里抠出 aweme 列表"""
    try:
        j = json.loads(body)
    except Exception:
        return []
    if j.get("status_code") not in (0, None):
        return []
    out = []
    for row in (j.get("data") or []):
        if not isinstance(row, dict):
            continue
        aweme = row.get("aweme_info") or (row if row.get("aweme_id") else None)
        if aweme and aweme.get("aweme_id"):
            out.append(aweme)
    return out


def _aweme_to_trend(aweme: dict, keyword: str) -> dict[str, Any]:
    """把抖音 aweme 转成 trends 表格式"""
    stats = aweme.get("statistics") or {}
    video = aweme.get("video") or {}
    create_time = aweme.get("create_time")
    return {
        "platform": "douyin",
        "video_id": str(aweme["aweme_id"]),
        "title": aweme.get("desc"),
        "author": (aweme.get("author") or {}).get("nickname"),
        "author_id": (aweme.get("author") or {}).get("sec_uid"),
        "likes": stats.get("digg_count") or 0,
        "comments": stats.get("comment_count") or 0,
        "shares": stats.get("share_count") or 0,
        "duration": int((video.get("duration") or 0) / 1000) or None,
        "cover_url": ((video.get("cover") or {}).get("url_list") or [None])[0],
        "keywords": json.dumps([keyword], ensure_ascii=False),
        "published_at": (datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")
                         if create_time else None),
    }


def search(keyword: str, pages: int = 2, sort: str = "likes",
           delay_ms: int = 1200, timeout_s: int = 120) -> dict[str, Any]:
    """采集一个关键词。pages = 期望滚动轮数（约 10-16 条/轮）"""
    from playwright.sync_api import sync_playwright

    sort_type = SORT_MAP.get(sort, 2)
    deadline = time.time() + max(45, timeout_s)
    collected: dict[str, dict] = {}
    seen_urls: set[str] = set()
    rounds: list[dict] = []
    notes: list[str] = []

    def on_response(resp) -> None:
        if not any(m in resp.url for m in HIT_MARKERS):
            return
        if resp.url in seen_urls:
            return
        seen_urls.add(resp.url)
        try:
            body = resp.text()
        except Exception as exc:
            notes.append(f"读响应失败: {str(exc)[:60]}")
            return
        for aweme in _collect_from_body(body):
            sid = str(aweme["aweme_id"])
            if sid not in collected:
                collected[sid] = aweme

    with sync_playwright() as pw:
        c = ctx(pw)
        try:
            page = c.new_page()
            page.set_default_timeout(30000)
            page.on("response", on_response)
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            page.goto(SEARCH_URL.format(kw=keyword, st=sort_type),
                      wait_until="domcontentloaded", timeout=45000)
            target = max(20, pages * 12)
            stagnant = 0
            for i in range(max(3, pages * 3)):
                if time.time() > deadline:
                    notes.append("到达时间上限")
                    break
                page.wait_for_timeout(3000)
                before = len(collected)
                rounds.append({"round": i + 1, "count": len(collected)})
                print(f"  第 {i + 1} 轮: {len(collected)} 条", flush=True)
                if len(collected) >= target:
                    break
                stagnant = stagnant + 1 if len(collected) == before else 0
                if stagnant >= 3:
                    notes.append("连续 3 轮无新增（可能已到底或被风控）")
                    break
                try:
                    page.mouse.wheel(0, 1800)
                except Exception:
                    pass
                page.wait_for_timeout(delay_ms)
        finally:
            try:
                c.close()
            except Exception:
                pass

    # 转换为 trends 格式并入库
    items: list[dict] = []
    for aweme in collected.values():
        trend = _aweme_to_trend(aweme, keyword)
        items.append(trend)

    saved = save_trends(items)

    # 快照落盘（空结果不覆盖好快照）
    snapshot = {"keyword": keyword, "sort": sort, "rounds": rounds,
                "notes": notes, "items": items, "saved": saved}
    snap_path = STATE_DIR / f"search_{keyword}.json"
    if items:
        snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        fail_path = STATE_DIR / f"search_{keyword}.failed.json"
        fail_path.write_text(json.dumps({**snapshot, "failed_at": datetime.now().isoformat(),
                                         "note": "本次 0 条，未覆盖主快照"},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"⚠ 本次 0 条：保留原快照，诊断写入 {fail_path.name}", flush=True)

    for n in notes:
        print(f"  · {n}", flush=True)
    return snapshot


def save_trends(items: list[dict]) -> int:
    """写入 trends 表（video_id 唯一，冲突则更新统计）"""
    if not items:
        return 0
    saved = 0
    with connect() as conn:
        for it in items:
            conn.execute("""
                INSERT INTO trends (platform, video_id, title, author, author_id,
                                    likes, comments, shares, duration, cover_url, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    likes = excluded.likes,
                    comments = excluded.comments,
                    shares = excluded.shares,
                    updated_at = CURRENT_TIMESTAMP
            """, (it["platform"], it["video_id"], it["title"], it["author"], it["author_id"],
                  it["likes"], it["comments"], it["shares"], it["duration"],
                  it["cover_url"], it["keywords"]))
            saved += 1
        conn.commit()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="抖音关键词搜索采集")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--pages", type=int, default=2, help="滚动轮数")
    parser.add_argument("--sort", default="likes", choices=list(SORT_MAP.keys()), help="排序方式")
    args = parser.parse_args()

    print(f"🔍 搜索: {args.keyword}（{args.sort}）", flush=True)
    result = search(args.keyword, args.pages, args.sort)

    print(f"\n汇总：{len(result['items'])} 条，入库 {result['saved']} 条", flush=True)
    top = sorted(result["items"], key=lambda x: x["likes"] or 0, reverse=True)[:5]
    for t in top:
        print(f"  ♥{t['likes']:>7}  {str(t['title'])[:46]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
