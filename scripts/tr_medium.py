"""medium 模型转写（复核读音/台词用）

用法: .venv/Scripts/python.exe scripts/tr_medium.py <wav|mp4> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel

wav = sys.argv[1]
out = Path(sys.argv[2])
model = WhisperModel(
    "medium", device="cpu", compute_type="int8",
    download_root=r"C:\Users\xxx13\.cache\modelscope\Systran",
)
segs, info = model.transcribe(wav, language="zh", beam_size=5, vad_filter=False)
rows = []
for s in segs:
    rows.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
    print(f"[{s.start:6.2f}-{s.end:6.2f}] {s.text.strip()}", flush=True)
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("SAVED", out)
