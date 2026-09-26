"""洗脑 10 连 — 成片验收：记忆点三变体是否都念到 + 逐句命中率

用法： .venv/Scripts/python.exe tools/check_xinao10_takes.py X1_yimiaosanzhe [uid2 ...]
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[^\u4e00-\u9fff]")


def norm(s: str) -> str:
    return CJK.sub("", s)


def best_hit(line: str, hyp: str) -> float:
    """在转写全文中滑窗找最像的片段（考虑 whisper 同音字误识）"""
    n = len(line)
    best = 0.0
    for w in range(max(1, n - 3), n + 4):
        for i in range(0, max(1, len(hyp) - w + 1)):
            best = max(best, difflib.SequenceMatcher(None, line, hyp[i:i + w]).ratio())
            if best >= 0.999:
                return best
    return best


def main() -> None:
    uids = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not uids:
        print("用法：check_xinao10_takes.py <uid> [...]")
        return
    data = json.loads((ROOT / "state/_xinao10_lines.json").read_text(encoding="utf-8"))
    for uid in uids:
        it = next((x for x in data["items"] if x["uid"] == uid), None)
        if not it:
            print(f"✗ 未知 uid：{uid}")
            continue
        tr = ROOT / f"out/gen_{uid}/transcripts/onetake_trim.json"
        if not tr.exists():
            print(f"✗ {uid} 无转写：{tr}")
            continue
        d = json.loads(tr.read_text(encoding="utf-8"))
        segs = d if isinstance(d, list) else d.get("segments", [])
        hyp = norm("".join(s.get("text", "") for s in segs))
        exp = [l for l in it["lines"]]
        print(f"\n{'=' * 56}\n▶ {uid}《{it['title']}》｜转写 {len(segs)} 段 / 台词 {len(exp)} 句")
        variants = [exp[1], exp[3], exp[5]]
        hit_all = True
        for i, line in enumerate(exp, 1):
            h = best_hit(norm(line), hyp)
            mark = "✓" if h >= 0.75 else ("·" if h >= 0.6 else "✗")
            if h < 0.75:
                hit_all = False
            tag = "  ← 记忆点" if i in (2, 4, 6) else ""
            print(f"  {mark} 句{i} 命中 {h:.2f}｜{line}{tag}")
        vh = [round(best_hit(norm(v), hyp), 2) for v in variants]
        print(f"  → 记忆点三变体命中 {vh} ｜ " + ("洗脑点完整 ✓" if min(vh) >= 0.7 else "⚠️ 有变体没念到，查看该镜"))
        print(f"  → 全句命中{'完整 ✓' if hit_all else '不完整 ⚠️（whisper 同音字误识属常态，低于 0.6 才需看片）'}")


if __name__ == "__main__":
    main()
