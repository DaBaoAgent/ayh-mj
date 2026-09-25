"""双音色验收：视频 → 指定时间窗口的基频中位数（判男/女声是否配对）

用法:
  python tools/check_dual_voice.py <video.mp4> 0,2.4 2.6,5
  （两个窗口：前段/后段，逗号分隔秒）
输出每段话音基频中位数（Hz）：
  · 成年男性约 95-155 Hz；成年女性约 190-280 Hz（H3 音频用自相关有系统性高估，看相对差异）
"""
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

import numpy as np


def extract_wav(video: str, out_wav: Path, sr: int = 16000) -> Path:
    subprocess.run([ffmpeg(), "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", str(sr),
                    str(out_wav)], capture_output=True, text=True, errors="replace")
    if not out_wav.exists():
        raise RuntimeError("ffmpeg 抽取音频失败")
    return out_wav


def read_wav(path: Path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    return sr, data


def f0_median(x: np.ndarray, sr: int, frame: float = 0.04, hop: float = 0.02,
              fmin: int = 70, fmax: int = 400) -> float | None:
    nf, nh = int(frame * sr), int(hop * sr)
    lo, hi = int(sr / fmax), int(sr / fmin)
    vals = []
    for start in range(0, max(1, len(x) - nf), nh):
        seg = x[start:start + nf]
        if len(seg) < nf // 2:
            break
        seg = seg - seg.mean()
        if float(np.max(np.abs(seg))) < 0.02:  # 静音帧
            continue
        corr = np.correlate(seg, seg, "full")[len(seg) - 1:]
        win = corr[lo:hi]
        if win.size == 0:
            continue
        peak = int(np.argmax(win)) + lo
        if corr[peak] <= 0.25 * corr[0]:  # 太弱
            continue
        vals.append(sr / peak)
    if not vals:
        return None
    return round(float(np.median(vals)), 1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    video = sys.argv[1]
    windows = sys.argv[2:] or []
    wav = extract_wav(video, ROOT / "out" / "tests" / "_dualvoice.wav")
    sr, data = read_wav(wav)
    print(f"音频: {len(data)/sr:.2f}s @ {sr}Hz")
    for spec in windows:
        t0, t1 = [float(v) for v in spec.split(",")]
        seg = data[int(t0 * sr):int(t1 * sr)]
        f0 = f0_median(seg, sr)
        kind = "?" if f0 is None else ("疑似男声" if f0 < 175 else "疑似女声")
        print(f"  窗口 {t0}-{t1}s: 基频中位数 = {f0} Hz  → {kind}")


if __name__ == "__main__":
    main()
