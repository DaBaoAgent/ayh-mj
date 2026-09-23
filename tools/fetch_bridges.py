"""短剧桥段/同行爆款/跨赛道爆款 抓取与桥段库维护

每天 cron 调用（配合 fetch_trends_multi）：
  1. 从热搜全量筛"剧情/短剧/热梗"相关条目 → 桥段候选
  2. 去重追加 assets/scripts/bridges.jsonl（agent 随后用 web_search 补充提炼）
  3. 桥段库按"新鲜度 + 注入轮换"供给文案生成（copybook.bridges_brief）
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
BRIDGES = ROOT / "assets" / "scripts" / "bridges.jsonl"

# 桥段/剧情相关关键词
BRIDGE_KEYS = ["短剧", "剧情", "反转", "名场面", "热梗", "霸总", "战神", "爽剧",
               "狗血", "土味", "逆袭", "打脸", "悬疑", "热播", "追剧", "大结局",
               "电视剧", "电影", "综艺", "演技", "杀青", "剧组"]


def _load_existing() -> set[str]:
    if not BRIDGES.exists():
        return set()
    out = set()
    for ln in BRIDGES.read_text(encoding="utf-8").splitlines():
        try:
            out.add(json.loads(ln).get("title", ""))
        except Exception:
            continue
    return out


def append_bridge(title: str, source: str, tags: list[str], pattern: str = "") -> bool:
    """追加一条桥段（去重）"""
    if not title.strip():
        return False
    existing = _load_existing()
    if title in existing:
        return False
    BRIDGES.parent.mkdir(parents=True, exist_ok=True)
    rec = {"date": datetime.now().strftime("%Y-%m-%d"), "title": title.strip(),
           "source": source, "tags": tags, "pattern": pattern,
           "injected": 0, "used": 0}
    with BRIDGES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def main() -> None:
    print("=" * 60)
    print("桥段/爆款抓取（热搜筛）")
    print("=" * 60)

    # 复用多平台抓取
    from fetch_trends_multi import _clean, fetch_baidu, fetch_bilibili, fetch_tencent, fetch_toutiao
    added = 0
    for src, fn in [("bilibili", fetch_bilibili), ("toutiao", fetch_toutiao),
                    ("baidu", fetch_baidu), ("tencent", fetch_tencent)]:
        try:
            items = fn()
        except Exception as e:
            print(f"  ⚠ {src} 失败: {str(e)[:80]}")
            continue
        for it in items:
            title = _clean(it.get("title", ""))
            hits = [k for k in BRIDGE_KEYS if k in title]
            if hits and append_bridge(title, src, hits):
                added += 1
                print(f"  + [{src}] {title[:48]}", flush=True)
    print(f"\n✓ 新增桥段候选 {added} 条 → {BRIDGES}")


if __name__ == "__main__":
    main()
