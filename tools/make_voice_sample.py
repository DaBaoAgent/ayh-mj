"""从长音频切出音色样本（12-15s 干净连续人声段）

流程：
  1) faster-whisper 转写 → 段落时间戳
  2) 找「连续说话 ≥ MIN_LEN 秒、段间静音 < 0.6s」的窗口
  3) ffmpeg 切出 + loudnorm 归一 → assets/cast/voice/<name>_v2.mp3

用法:
  .venv/Scripts/python.exe tools/make_voice_sample.py out/voices/xxx.mp3 -o assets/cast/voice/elder_v2.mp3 [--min 12] [--start 0]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--min", type=float, default=12.0, help="最短连续说话时长(秒)")
    ap.add_argument("--skip", type=float, default=0.0, help="跳过开头的秒数（避开片头/BGM）")
    args = ap.parse_args()

    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, info = model.transcribe(args.audio, language="zh", vad_filter=True)
    segs = list(segs)
    print(f"共 {len(segs)} 段，总时长 {info.duration:.1f}s", flush=True)

    # 找连续窗口
    best = None
    i = 0
    while i < len(segs):
        j = i
        while j + 1 < len(segs) and (segs[j + 1].start - segs[j].end) < 0.6:
            j += 1
        span = segs[j].end - segs[i].start
        if span >= args.min and segs[i].start >= args.skip:
            if best is None or span < 14.5:  # 优先接近 13s
                best = (segs[i].start, segs[j].end, span, " ".join(s.text.strip() for s in segs[i:j+1]))
                if span <= 14.5:
                    break
        i = j + 1

    if not best:
        print("✗ 未找到足够长的连续人声段——可降低 --min")
        raise SystemExit(1)

    start, end, span, text = best
    dur = min(13.0, span)
    print(f"✓ 选中片段: {start:.1f}s 起，时长 {span:.1f}s（取 {dur:.1f}s）", flush=True)
    print(f"  文本: {text[:80]}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([
        ffmpeg(), "-y", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", args.audio,
        "-af", "loudnorm=I=-18:TP=-2:LRA=9", "-ar", "32000", "-ac", "1", "-b:a", "96k", str(out),
    ], capture_output=True, text=True)
    print(f"{'✓' if out.exists() else '✗'} 样本: {out} {out.stat().st_size//1024 if out.exists() else 0}KB", flush=True)


if __name__ == "__main__":
    main()
