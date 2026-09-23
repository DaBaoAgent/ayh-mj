"""多平台热点抓取 → 热点库扩充到 100 条

平台（不扫码、公开接口）：B站热搜 / 今日头条热榜 / 百度热榜 / 腾讯新闻热点
筛选：与"老人/出行/健康/家庭"相关度评分；不足 100 条时用常青选题补齐
归档：state/jobs.db trends 表 + assets/trends/热点库.md
"""
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.state import connect

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "assets" / "trends" / "热点库.md"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# ── 相关度关键词分级 ──────────────────────────────────────
KEY_STRONG = ["轮椅", "代步车", "养老", "老人", "老年人", "爸妈", "父母", "康复",
              "残疾", "助残", "腿脚", "敬老", "银发", "老龄", "照护", "失能"]
KEY_MED = ["健康", "医院", "看病", "医保", "退休", "爷爷", "奶奶", "孝顺", "孝心",
           "家庭", "亲情", "陪伴", "护理", "养生", "锻炼", "散步", "公园"]
KEY_SOFT = ["出行", "交通", "智能", "科技", "消费", "礼物", "惊喜", "省钱", "实用",
            "安全", "生活", "家务", "小区", "社区", "邻居", "广场舞"]


def _curl(url: str, timeout: int = 15) -> str:
    r = subprocess.run(["curl", "-s", "-m", str(timeout), url, "-H", f"User-Agent: {UA}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout or ""


def fetch_bilibili() -> list[dict]:
    txt = _curl("https://api.bilibili.com/x/web-interface/search/square?limit=50")
    try:
        data = json.loads(txt)
        lst = data["data"]["trending"]["list"]
        return [{"title": x.get("show_name") or x.get("keyword", ""), "src": "bilibili"} for x in lst]
    except Exception as e:
        print(f"  ⚠ bilibili 解析失败: {str(e)[:80]}", flush=True)
        return []


def fetch_toutiao() -> list[dict]:
    txt = _curl("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    try:
        data = json.loads(txt)
        return [{"title": x.get("Title", ""), "src": "toutiao"} for x in data.get("data", [])]
    except Exception as e:
        print(f"  ⚠ toutiao 解析失败: {str(e)[:80]}", flush=True)
        return []


def fetch_baidu() -> list[dict]:
    txt = _curl("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    try:
        data = json.loads(txt)
        out = []
        for card in data["data"]["cards"]:
            for node in card.get("content", []):
                # 结构可能一层或两层嵌套
                subs = node.get("content") if isinstance(node, dict) and isinstance(node.get("content"), list) else [node]
                for sub in subs:
                    if not isinstance(sub, dict):
                        continue
                    w = sub.get("word") or sub.get("query") or ""
                    if w:
                        out.append({"title": w, "src": "baidu"})
        return out
    except Exception as e:
        print(f"  ⚠ baidu 解析失败: {str(e)[:80]}", flush=True)
        return []


def fetch_tencent() -> list[dict]:
    txt = _curl("https://r.inews.qq.com/gw/event/hot_ranking_list?page_size=50")
    try:
        data = json.loads(txt)
        out = []
        for grp in data.get("idlist", []):
            for n in grp.get("newslist", []):
                t = n.get("title", "")
                if t and "腾讯新闻用户最关注" not in t:
                    out.append({"title": t, "src": "tencent"})
        return out
    except Exception as e:
        print(f"  ⚠ tencent 解析失败: {str(e)[:80]}", flush=True)
        return []


def _clean(title: str) -> str:
    t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", title)  # emoji
    return re.sub(r"\s+", " ", t).strip()


def score_title(title: str, rank: int) -> tuple[float, int, list[str]]:
    """(score, matched, keywords) — 热榜排名越前微加分"""
    hits_strong = [k for k in KEY_STRONG if k in title]
    hits_med = [k for k in KEY_MED if k in title]
    hits_soft = [k for k in KEY_SOFT if k in title]
    rank_bonus = max(0, (50 - rank)) * 0.2
    if hits_strong:
        return 88 + rank_bonus, 1, hits_strong + hits_med
    if hits_med:
        return 72 + rank_bonus, 1, hits_med
    if hits_soft:
        return 55 + rank_bonus, 0, hits_soft
    return 40 + rank_bonus, 0, []


# ── 常青选题（真实热点不足 100 时补齐；可绑产品且不过时）──────────
EVERGREEN = [
    "爸妈的旧物件你劝不动？那是他们的安全感", "老人最怕的不是花钱，是失去自己出门的自由",
    "给爸妈买东西，实用永远比贵重要", "腿脚不便之后，生活质量差在哪",
    "父母的'凑合用'里藏着多少将就", "为什么老人抗拒换掉用了十年的旧东西",
    "一个人也能出门的底气，来自什么", "老人独自出门，家人最担心的三件事",
    "爸妈嘴上说不要，身体却很诚实的瞬间", "上一辈的节俭，让人心疼还是无奈",
    "父母年纪大了，什么才是真正的孝顺", "老人摔倒之后，全家生活都变了",
    "能自己出门的老人，精神状态都不一样", "帮爸妈挑出行工具，最该看哪三点",
    "老人的面子：不想麻烦子女是最大的倔强", "十年老物件 vs 新科技，爸妈怎么选",
    "家里有老人，这些安全问题别忽视", "老旧代步工具的隐患，你知道吗",
    "爸妈的出行半径，决定晚年幸福感", "老人用新玩意，学得会吗",
    "给爸妈的第一件智能装备该买什么", "老年人的生活，也可以很便捷",
    "父母不肯搬来同住？给他们更好的独立条件", "上了年纪的人，最需要的是'不费力'",
    "老人的日常：买菜/遛弯/接孙辈，工具趁手吗", "别让'怕麻烦'困住爸妈的脚步",
    "爸妈学会用新东西后的炫耀瞬间", "适老化改造，从出行开始",
    "老人出门的两难：麻烦人 vs 靠自己", "退休生活过得好不好，看这几点",
]


def main() -> None:
    print("=" * 60)
    print("多平台热点抓取 → 热点库扩充")
    print("=" * 60)

    all_items: list[dict] = []
    for name, fn in [("B站", fetch_bilibili), ("头条", fetch_toutiao),
                     ("百度", fetch_baidu), ("腾讯", fetch_tencent)]:
        items = fn()
        print(f"  {name}: {len(items)} 条原始", flush=True)
        for i, it in enumerate(items):
            it["rank"] = i + 1
        all_items.extend(items)

    # 评分 + 清洗 + 去重
    seen: set[str] = set()
    scored: list[dict] = []
    for it in all_items:
        title = _clean(it["title"])
        if not title or title in seen:
            continue
        seen.add(title)
        score, matched, kws = score_title(title, it["rank"])
        scored.append({"title": title, "src": it["src"], "score": round(score, 1),
                       "matched": matched, "keywords": kws})

    scored.sort(key=lambda x: -x["score"])
    hot_hits = [s for s in scored if s["score"] >= 55]
    print(f"\n  去重后 {len(scored)} 条；相关命中 {len(hot_hits)} 条（含软相关）", flush=True)

    # 不足 100 条 → 常青选题补齐（手工30 + LLM生成50）
    final = list(hot_hits[:100])
    if len(final) < 100:
        need = 100 - len(final)
        pool = list(EVERGREEN)
        extra_f = ROOT / "assets" / "trends" / "evergreen_extra.json"
        if extra_f.exists():
            import contextlib
            with contextlib.suppress(Exception):
                pool += json.loads(extra_f.read_text(encoding="utf-8"))
        # 排除已用过的（去重库）
        try:
            from lib.ideas import used_hotspots
            used = used_hotspots()
            pool = [t for t in pool if t not in used]
        except Exception:
            pass
        for t in pool[:need]:
            final.append({"title": t, "src": "evergreen", "score": 62.0,
                          "matched": 1, "keywords": ["常青"]})
        print(f"  + 常青选题补齐 {min(need, len(pool))} 条（池{len(pool)}）", flush=True)
    # 截到 100
    final = final[:100]

    # ── 入库 ──
    inserted = skipped = 0
    with connect() as conn:
        for item in final:
            vid = f"{item['src']}_{hashlib.md5(item['title'].encode()).hexdigest()[:10]}"
            exists = conn.execute(
                "SELECT id FROM trends WHERE title = ?", (item["title"],)).fetchone()
            if exists:
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO trends (platform, video_id, title, likes, keywords, score, matched) "
                "VALUES (?,?,?,?,?,?,?)",
                (item["src"], vid, item["title"], 0,
                 json.dumps(item["keywords"], ensure_ascii=False),
                 item["score"], item["matched"]))
            inserted += 1
    print(f"\n  ✓ 入库 {inserted} 条（跳过重复 {skipped}）", flush=True)

    # ── 归档 md ──
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# 热点库（{datetime.now().strftime('%Y-%m-%d')} 多平台抓取）", "",
             f"> 来源：B站/头条/百度/腾讯热榜 + 常青选题 | 共 {len(final)} 条", ""]
    for i, it in enumerate(final, 1):
        tag = {"evergreen": "常青"} .get(it["src"], it["src"])
        match = "✓" if it["matched"] else "·"
        lines.append(f"{i:3d}. [{tag}] {match} {it['score']:5.1f} | {it['title']}")
    ARCHIVE.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ 归档 {ARCHIVE}", flush=True)

    # ── 汇总 ──
    print("\n=== 结果分布 ===")
    from collections import Counter
    c = Counter(it["src"] for it in final)
    for k, v in c.most_common():
        print(f"  {k}: {v}")
    strong = sum(1 for it in final if it["score"] >= 85)
    print(f"  强相关(≥85): {strong} | 中相关(70-85): "
          f"{sum(1 for it in final if 70 <= it['score'] < 85)} | "
          f"其余: {sum(1 for it in final if it['score'] < 70)}")


if __name__ == "__main__":
    main()
