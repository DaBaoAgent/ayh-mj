"""短剧狗血10连 — 批量转写验收（medium）+ 逐字一致率自动比对

用法： .venv/Scripts/python.exe tools/verify_batch_duikang10.py
产出： state/batch_duikang10_transcripts.json
      控制台打印每条：转写段 / 期望台词 / 一致率（Levenshtein）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from faster_whisper import WhisperModel  # noqa: E402
from prep_duikang10 import SCRIPTS, TITLES  # noqa: E402


def norm(x: str) -> str:
    return re.sub(r"[^\u3400-\u9fff]", "", x)


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def main() -> None:
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    out, bad = {}, []
    for s in SCRIPTS:
        uid = s["uid"]
        p = ROOT / f"out/gen_job_{uid}/onetake.mp4"
        if not p.exists():
            print(f"✗ {uid} 无文件"); continue
        segs, _ = model.transcribe(str(p), language="zh", vad_filter=True)
        rows = [{"start": round(x.start, 2), "end": round(x.end, 2), "text": x.text.strip()} for x in segs]
        out[uid] = rows
        expect = "".join(t for sh in s["shots"] for _, t in sh["lines"])
        got = "".join(r["text"] for r in rows)
        ne, ng = norm(expect), norm(got)
        acc = 1 - lev(ne, ng) / max(len(ne), 1)
        flag = "✅" if acc >= 0.999 else ("⚠️" if acc >= 0.9 else "❌")
        if acc < 0.999:
            bad.append((uid, round(acc, 3)))
        print(f"\n{flag} {uid} {TITLES[uid]} 一致率 {acc * 100:.1f}%  转写{len(rows)}段/台词{sum(len(x['lines']) for x in s['shots'])}句")
        for r in rows:
            print(f"   [{r['start']:5.2f}-{r['end']:5.2f}] {r['text']}")
        if acc < 0.999:
            print(f"   期望：{expect}")
            print(f"   实得：{got}")
    (ROOT / "state/batch_duikang10_transcripts.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✓ 已存 state/batch_duikang10_transcripts.json（{len(out)} 条）")
    print(f"需复核（<100%）：{bad if bad else '无'}")


if __name__ == "__main__":
    main()
