"""追加 web 提炼的桥段模式到 assets/scripts/bridges.jsonl（同名 title 跳过）"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FP = ROOT / "assets" / "scripts" / "bridges.jsonl"
DATE = "2026-09-24"

NEW = [
    {"title": "短剧双层马甲掉马爽点", "tags": ["短剧"],
     "pattern": "先以被轻视的小人物身份铺垫压制→关键时刻隐藏大佬身份当众掉马→围观者从鄙夷转为震惊拜服"},
    {"title": "饭局铁证当众打脸", "tags": ["短剧"],
     "pattern": "亲人当众道德绑架索取→主角隐忍布局→掏出转账记录/录音铁证公开→吸血者颜面扫地"},
    {"title": "弱势工具被玩成潮流反差", "tags": ["同行", "跨赛道"],
     "pattern": "本该属于行动不便人群的工具→被主角玩出通勤/越野新用途→金句式口号+路人围观惊叹"},
    {"title": "数字冲击开头反差反转", "tags": ["跨赛道"],
     "pattern": "数字冲击开头（X分钟/X公里）→本以为做不到的反差反转→行动号召"},
    {"title": "被质疑后实测数据打脸", "tags": ["同行"],
     "pattern": "先被质疑或被提醒安全风险→主角现场实测公布数据→质疑者当场改口认可"},
]

existing = set()
if FP.exists():
    for line in FP.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            existing.add(json.loads(line).get("title", ""))
        except json.JSONDecodeError:
            pass

added = skipped = 0
with FP.open("a", encoding="utf-8", newline="\n") as f:
    for it in NEW:
        if it["title"] in existing:
            print(f"  跳过同名: {it['title']}")
            skipped += 1
            continue
        rec = {"date": DATE, "title": it["title"], "source": "web",
               "tags": it["tags"], "pattern": it["pattern"], "injected": 0, "used": 0}
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        existing.add(it["title"])
        added += 1
        print(f"  + {it['title']}")

total = sum(1 for l in FP.read_text(encoding="utf-8").splitlines() if l.strip())
print(f"\n  ✓ 新增 {added} 条（跳过 {skipped}）| 桥段库总数 {total} 条")
