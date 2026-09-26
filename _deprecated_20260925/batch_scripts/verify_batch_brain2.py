"""脑洞10连第二批 — 批量转写验收（medium 逐句）"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from faster_whisper import WhisperModel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
UIDS = [
    "B2_01_kuaidi", "B2_02_diaoyu", "B2_03_luying", "B2_04_chongdian", "B2_05_xueche",
    "B2_06_zhaiXiang", "B2_07_jiedian", "B2_08_nianhuo", "B2_09_xiuche", "B2_10_jiaoChe",
]

model = WhisperModel("medium", device="cpu", compute_type="int8")
out = {}
for uid in UIDS:
    p = ROOT / f"out/gen_job_{uid}/onetake.mp4"
    if not p.exists():
        print(f"✗ {uid} 无文件"); continue
    segs, _ = model.transcribe(str(p), language="zh", vad_filter=True)
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]
    out[uid] = rows
    print(f"\n=== {uid} ===")
    for r in rows:
        print(f"  [{r['start']:5.2f}-{r['end']:5.2f}] {r['text']}")
Path(ROOT / "state/batch_brain2_transcripts.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n✓ 已存 state/batch_brain2_transcripts.json（{len(out)} 条）")
