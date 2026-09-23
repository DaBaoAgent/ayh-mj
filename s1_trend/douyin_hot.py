"""抖音热榜采集（官方接口，页面自动签名）

原理（来自 AutoAYH 实战）：
  · 打开 douyin.com 首页 → 浏览器自己请求 /aweme/v1/web/hot/search/list/
  · 返回 51 个热词，含 hot_value / sentence_id
  · 适老相关性排序（轮椅/养老/出行关键词加权），选择 top_n 进详情

用法：
    python s1_trend/douyin_hot.py --top 8
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from lib import STATE_DIR
from s1_trend.browser import ctx

RELEVANCE_KEYS = ["老", "养老", "轮椅", "适老", "父亲", "母亲", "爸妈",
                  "奶奶", "爷爷", "出行", "健康", "医院", "家", "带娃", "孝"]


def fetch_hot_words(top_n: int = 8) -> dict[str, Any]:
    """抓取热榜词（带适老相关性排序）"""
    from playwright.sync_api import sync_playwright

    box: dict[str, Any] = {}

    with sync_playwright() as pw:
        c = ctx(pw)
        try:
            page = c.new_page()

            def on_resp(resp) -> None:
                u = resp.url.split("?")[0]
                try:
                    if "hot/search/list" in u:
                        box["hot"] = resp.json()
                except Exception:
                    return

            page.on("response", on_resp)
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(8000)
        finally:
            c.close()

    hot = box.get("hot") or {}
    words = ((hot.get("data") or {}).get("word_list")) or hot.get("word_list") or []
    print(f"热榜词数: {len(words)}", flush=True)

    def relevance(w: dict) -> int:
        text = w.get("word") or ""
        return sum(2 for k in RELEVANCE_KEYS if k in text)

    ranked = sorted(words, key=lambda w: (relevance(w), w.get("hot_value") or 0), reverse=True)
    picked = [w for w in ranked if w.get("sentence_id")][:top_n]

    # 落盘快照
    snapshot = {
        "fetched_at": datetime.now().isoformat(),
        "total": len(words),
        "words": words,
        "picked": [{"word": w.get("word"), "sentence_id": w.get("sentence_id"),
                    "hot_value": w.get("hot_value")} for w in picked],
    }
    snap = STATE_DIR / "douyin_hot.json"
    snap.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    print("适老相关热词:", [w["word"] for w in picked], flush=True)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="抖音热榜采集")
    parser.add_argument("--top", type=int, default=8, help="选取热词数量")
    args = parser.parse_args()

    print("🔥 抓取抖音热榜...", flush=True)
    result = fetch_hot_words(args.top)
    print(f"\n✓ 完成：热词 {result['total']} 个，适老相关 {len(result['picked'])} 个", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
