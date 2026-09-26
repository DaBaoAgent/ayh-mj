"""洗脑 10 连台词预检：字数 / 单句长度 / 禁用符号 / 撞车"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import check_collision as cc  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")
BAD_CHARS = re.compile(r"[\d—–\-?!;:]")

data = json.loads((ROOT / "state" / "_xinao10_lines.json").read_text(encoding="utf-8"))
corpus = cc.harvest({"scripts-洗脑10连-G3-20260926.md"}, set())

print(f"语料库：{len(corpus)} 句（已拍）\n")
all_lines = []
total_hits = 0
for it in data["items"]:
    lines = it["lines"]
    counts = [len(CJK.findall(x)) for x in lines]
    memo = it["memo"]
    memo_n = sum(1 for x in lines if memo in x)
    variants = [lines[1], lines[3], lines[5]]
    dup_variant = len(set(variants)) < 3
    if dup_variant:
        print("   ⚠️ 记忆点三变体有重复 → 门禁 R4 会 ERROR")
    bad = [x for x in lines if BAD_CHARS.search(x)]
    over = [x for x, c in zip(lines, counts) if c > 13]
    print(f"── {it['uid']}《{it['title']}》 {it['point']} · {it['angle']} · {it['group']}")
    print(f"   字数 {sum(counts)}（65-72）｜ 单句 {counts} ｜ 最长 {max(counts)}")
    print(f"   记忆点关键词「{memo}」命中 {memo_n} 次" + ("" if memo_n >= 3 else "  ⚠️ 应≥3次"))
    if bad:
        print(f"   ⚠️ 含禁用字符：{bad}")
    if over:
        print(f"   ⚠️ 超13字：{over}")
    hits = cc.report(lines, corpus)
    total_hits += hits
    all_lines += lines
    print()

print(f"=== 汇总：撞车拦截 {total_hits} 句 / 总台词 {len(all_lines)} 句 ===")
