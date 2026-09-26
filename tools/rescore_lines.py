"""台词逐句对账（通用版：读缓存转写复算，不重跑 whisper）——改比对规则后秒级复算

台词来源优先级：docs/onetake_lines_<uid>.txt → 否则从 docs/onetake_check_<uid>.txt 里抽 <d>[Chinese] …</d>
转写来源：out/gen_<uid>/transcript_medium.json（各验收脚本跑过就会留下）

用法：
  .venv/Scripts/python.exe tools/rescore_lines.py <uid> [<uid> ...]
  .venv/Scripts/python.exe tools/rescore_lines.py --all        # 扫 out/gen_* 全部
输出：每段一致率 + 缺失句清单（繁转简 + 品牌名同音误听白名单）
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.zh_norm import normalize_cn  # noqa: E402

VOICE_FIX = {"爱犹护": "爱优护", "爱悠护": "爱优护", "爱忧护": "爱优护", "爱邮户": "爱优护",
             "爱游护": "爱优护", "亲变侠": "轻便侠", "清便暇": "轻便侠", "轻便暇": "轻便侠",
             "轻便辖": "轻便侠", "轻便霞": "轻便侠", "轻便狭": "轻便侠"}
D_RE = re.compile(r"<d>\[Chinese\]\s*(.*?)\s*</d>")


def fix(s: str) -> str:
    for k, v in VOICE_FIX.items():
        s = s.replace(k, v)
    return s


def lines_of(uid: str) -> list[str]:
    p = ROOT / f"docs/onetake_lines_{uid}.txt"
    if p.exists():
        return [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    c = ROOT / f"docs/onetake_check_{uid}.txt"
    if c.exists():
        return [m.group(1) for m in D_RE.finditer(c.read_text(encoding="utf-8"))]
    return []


def main() -> None:
    args = sys.argv[1:]
    if "--all" in args or not args:
        uids = sorted(p.parent.name[len("gen_"):] for p in ROOT.glob("out/gen_*/transcript_medium.json"))
    else:
        uids = args
    if not uids:
        print("没有可复算的任务（需要 out/gen_<uid>/transcript_medium.json）")
        return
    print(f"{'任务':<34}{'句数':<6}{'一致率':<9}缺失句")
    missing_all: list[tuple[str, str]] = []
    for uid in uids:
        tp = ROOT / f"out/gen_{uid}/transcript_medium.json"
        lines = lines_of(uid)
        if not tp.exists() or not lines:
            print(f"{uid:<34}{'—':<6}{'—':<9}(缺转写或缺台词清单)")
            continue
        got = fix(normalize_cn("".join(r["text"] for r in json.loads(tp.read_text(encoding="utf-8")))))
        exp = fix(normalize_cn("".join(lines)))
        missing = []
        for t in lines:
            k = normalize_cn(t)
            if k in got or any(k[i:i + 4] in got for i in range(max(len(k) - 3, 1))):
                continue
            missing.append(t)
        ratio = difflib.SequenceMatcher(None, exp, got).ratio()
        print(f"{uid:<34}{len(lines):<6}{ratio:<9.3f}{missing if missing else '无'}")
        missing_all += [(uid, m) for m in missing]
    print(f"\n缺失合计 {len(missing_all)} 句" + (f"：{missing_all}" if missing_all else ""))


if __name__ == "__main__":
    main()
