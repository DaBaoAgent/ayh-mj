"""BGM 指纹识别（Shazam）+ 多窗口扫描

用法: .venv/Scripts/python.exe scripts/identify_bgm.py <音频/视频> [--wins 0-12,20-32,...]

对每个窗口切一段音频送 Shazam，汇总命中的曲名/艺人/专辑，并给出最佳命中窗口。
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


def clip(src: Path, start: float, dur: float, out: Path) -> Path:
    subprocess.run(
        [ffmpeg(), "-y", "-loglevel", "error", "-ss", str(start), "-t", str(dur),
         "-i", str(src), "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(out)],
        capture_output=True, timeout=300,
    )
    return out


async def main() -> None:
    src = Path(sys.argv[1])
    wins_arg = sys.argv[sys.argv.index("--wins") + 1] if "--wins" in sys.argv else ""
    if wins_arg:
        windows = [tuple(float(x) for x in w.split("-")) for w in wins_arg.split(",")]
    else:
        # 默认：12 个 12 秒窗口，全程平铺（重叠覆盖）
        windows = [(i * 6.0, 12.0) for i in range(12)]

    shazam = Shazam()
    hits: dict[str, dict] = {}
    tmpdir = Path(tempfile.mkdtemp(prefix="bgm_"))
    for i, (start, dur) in enumerate(windows):
        wav = tmpdir / f"w{i:02d}.wav"
        clip(src, start, dur, wav)
        if wav.stat().st_size < 20000:
            print(f"  [{start:5.1f}s] 切片为空，跳过")
            continue
        try:
            res = await shazam.recognize(str(wav))
        except Exception as e:  # noqa: BLE001
            print(f"  [{start:5.1f}s] ✗ {type(e).__name__}: {e}")
            continue
        track = res.get("track") or {}
        title = track.get("title")
        if not title:
            print(f"  [{start:5.1f}s] 未识别")
            continue
        artist = track.get("subtitle")
        album = ((track.get("sections") or [{}])[0].get("metadata") or [])
        album_name = next((m["text"] for m in album if m.get("title") == "Album"), "")
        genres = next((m["text"] for m in album if m.get("title") == "Genre"), "")
        released = next((m["text"] for m in album if m.get("title") == "Released"), "")
        print(f"  [{start:5.1f}s] ✓ {title} — {artist} | 专辑:{album_name} | 风格:{genres} | 发行:{released}")
        hits.setdefault(title, {"title": title, "artist": artist, "album": album_name,
                                "genres": genres, "released": released, "windows": []})
        hits[title]["windows"].append(round(start, 1))

    print("\n=== 汇总 ===")
    for h in sorted(hits.values(), key=lambda x: -len(x["windows"])):
        print(f"{len(h['windows'])} 次命中 | {h['title']} — {h['artist']} | {h['album']} | {h['genres']} | {h['released']} | 窗口 {h['windows']}")
    out = src.parent / "bgm_identify.json"
    out.write_text(json.dumps(list(hits.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    print("SAVED", out)


if __name__ == "__main__":
    asyncio.run(main())
