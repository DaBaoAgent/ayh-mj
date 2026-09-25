"""音色对应分析：段落音频 vs 音色样本（频谱包络余弦相似度）

原理：音色差异主要体现在频谱包络（长期平均谱倾斜/共振峰），
对目标段落与候选样本各算「对数频带能量分布」，再比余弦相似度，得分更高者更像。

用法:
  python tools/voice_match.py <目标视频/音频> --seg 0.2,2.3 --seg 2.7,4.8 \
      --ref assets/cast/voice/son_voice.mp3 --ref assets/cast/voice/mother_voice.mp3
"""
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

import numpy as np


def to_wav(src: str, out: Path, sr: int = 16000) -> Path:
    subprocess.run([ffmpeg(), "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), str(out)],
                   capture_output=True)
    return out


def load(path: Path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return sr, x


def spectrum_signature(x: np.ndarray, sr: int, nfft: int = 1024, hop: int = 256,
                       nbins: int = 48) -> np.ndarray | None:
    """平均对数频带能量（48 个对数间隔频带，60-6000Hz）"""
    frames = []
    for s in range(0, max(1, len(x) - nfft), hop):
        seg = x[s:s + nfft] * np.hanning(nfft)
        if np.max(np.abs(seg)) < 0.02:
            continue
        frames.append(np.abs(np.fft.rfft(seg)) ** 2)
    if not frames:
        return None
    avg = np.mean(frames, axis=0)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    edges = np.geomspace(60, 6000, nbins + 1)
    sig = []
    for i in range(nbins):
        m = (freqs >= edges[i]) & (freqs < edges[i + 1])
        sig.append(avg[m].mean() if m.any() else 1e-12)
    sig = np.log(np.array(sig) + 1e-12)
    return (sig - sig.mean()) / (sig.std() + 1e-9)


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    args = sys.argv[1:]
    src = args[0]
    segs, refs = [], []
    i = 1
    while i < len(args):
        if args[i] == "--seg":
            segs.append(tuple(float(v) for v in args[i + 1].split(",")))
            i += 2
        elif args[i] == "--ref":
            refs.append(Path(args[i + 1]))
            i += 2
        else:
            i += 1

    tmp = ROOT / "out" / "tests"
    tmp.mkdir(parents=True, exist_ok=True)
    sr, data = load(to_wav(src, tmp / "_vm_target.wav"))

    ref_sigs = {}
    for r in refs:
        rsr, rx = load(to_wav(str(r), tmp / f"_vm_{r.stem}.wav"))
        ref_sigs[r.stem] = spectrum_signature(rx, rsr)

    print(f"目标: {Path(src).name}（{len(data)/sr:.2f}s）")
    for t0, t1 in segs:
        seg = data[int(t0 * sr):int(t1 * sr)]
        sig = spectrum_signature(seg, sr)
        if sig is None:
            print(f"  段 {t0}-{t1}s: 无有效音频")
            continue
        scores = {name: cos(sig, rsig) for name, rsig in ref_sigs.items() if rsig is not None}
        best = max(scores, key=scores.get)
        detail = "  ".join(f"{k}={v:.3f}" for k, v in scores.items())
        print(f"  段 {t0}-{t1}s: 最像 → {best}   [{detail}]")


if __name__ == "__main__":
    main()
