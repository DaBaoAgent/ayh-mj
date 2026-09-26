"""Shazam 完整曲目元数据（曲名/艺人/专辑/发行/封面/链接）

用法: .venv/Scripts/python.exe scripts/song_meta.py <音频或视频> [--ss 起始秒] [--t 时长]
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


async def main() -> None:
    src = Path(sys.argv[1])
    ss = float(sys.argv[sys.argv.index("--ss") + 1]) if "--ss" in sys.argv else 0.0
    dur = float(sys.argv[sys.argv.index("--t") + 1]) if "--t" in sys.argv else 12.0
    tmp = Path(tempfile.mkdtemp(prefix="song_")) / "clip.wav"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", str(ss), "-t", str(dur),
                    "-i", str(src), "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le",
                    str(tmp)], capture_output=True, timeout=300)

    sh = Shazam()
    raw = await sh.recognize(str(tmp))
    t = raw.get("track") or {}
    meta = {}
    for sec in t.get("sections") or []:
        for m in sec.get("metadata") or []:
            meta[m.get("title", "")] = m.get("text", "")
    out = {
        "title": t.get("title"),
        "artist": t.get("subtitle"),
        "shazam_url": t.get("url"),
        "cover": (t.get("images") or {}).get("coverart"),
        "metadata": meta,
        "apple_music": (t.get("hub") or {}).get("actions"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
