"""BGM 复核：多窗口重试直到命中，并打印完整 Shazam track 载荷

用法: .venv/Scripts/python.exe scripts/song_confirm.py <音频> [--tries 12]
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg  # noqa: E402

from shazamio import Shazam  # noqa: E402

WINDOWS = [(0, 10), (6, 12), (12, 12), (18, 12), (24, 12), (30, 12), (36, 12),
           (42, 12), (48, 12), (54, 12), (60, 12), (66, 11)]


async def main() -> None:
    src = Path(sys.argv[1])
    sh = Shazam()
    hits: list[dict] = []
    tmpdir = Path(tempfile.mkdtemp(prefix="confirm_"))
    for i, (ss, dur) in enumerate(WINDOWS):
        wav = tmpdir / f"c{i:02d}.wav"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", str(ss), "-t", str(dur),
                        "-i", str(src), "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le",
                        str(wav)], capture_output=True, timeout=300)
        try:
            raw = await sh.recognize(str(wav))
        except Exception as e:  # noqa: BLE001
            print(f"[{ss:5.1f}s] ✗ {type(e).__name__}")
            continue
        t = raw.get("track") or {}
        if not t.get("title"):
            print(f"[{ss:5.1f}s] 未识别")
            continue
        meta = {}
        for sec in t.get("sections") or []:
            for m in sec.get("metadata") or []:
                meta[m.get("title", "")] = m.get("text", "")
        print(f"[{ss:5.1f}s] ✓ {t.get('title')} — {t.get('subtitle')} | {meta}")
        hits.append({"window": ss, "title": t.get("title"), "artist": t.get("subtitle"),
                     "meta": meta, "url": t.get("url"),
                     "cover": (t.get("images") or {}).get("coverart")})
    out = Path(src).parent / "song_confirm.json"
    out.write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== 命中 {len(hits)}/{len(WINDOWS)} 窗口 ===")
    for h in hits:
        print(json.dumps(h, ensure_ascii=False))
    print("SAVED", out)


if __name__ == "__main__":
    asyncio.run(main())
