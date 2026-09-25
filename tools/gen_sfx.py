"""合成 3 个标准音效（叮/咻/啪）— ffmpeg 纯合成，零素材

输出: assets/sfx/ding.mp3 / whoosh.mp3 / pop.mp3
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

OUT = ROOT / "assets/sfx"
OUT.mkdir(parents=True, exist_ok=True)

JOBS = [
    # (输出, lavfi 输入, 滤镜)
    ("ding.mp3", "sine=frequency=1250:duration=0.45",
     "afade=t=out:st=0.03:d=0.40,volume=0.45"),
    ("whoosh.mp3", "anoisesrc=color=pink:duration=0.35:amplitude=0.5",
     "highpass=f=700,lowpass=f=6500,afade=t=in:st=0:d=0.06,afade=t=out:st=0.18:d=0.17,volume=0.38"),
    ("pop.mp3", "sine=frequency=190:duration=0.14",
     "afade=t=out:st=0.012:d=0.12,volume=0.55"),
]


def main() -> None:
    for name, src, af in JOBS:
        out = OUT / name
        subprocess.run([ffmpeg(), "-y", "-f", "lavfi", "-i", src, "-af", af,
                        "-ar", "32000", "-ac", "1", "-b:a", "96k", str(out)], capture_output=True)
        print(f"{'✓' if out.exists() else '✗'} {out.name}")


if __name__ == "__main__":
    main()
