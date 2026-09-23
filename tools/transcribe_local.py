"""本地转写（faster-whisper 直用，跳过 whisperx 的 alignment 环节）

背景：whisperx 的中文对齐模型（jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn）
在 hf-mirror 上拉不到 feature extractor 配置 → 对齐必失败。
本脚本直接用 whisperx 底层的 faster-whisper（small 模型已缓存）拿 segments 级时间戳，
足够 check-take.mjs 做逐字比对与语速估算。

用法：
    python tools/transcribe_local.py <视频路径>
    → 产出 <视频目录>/transcripts/<stem>.json（segments[] 结构）
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.tools import ffmpeg


def extract_audio(video: str, out_wav: str):
    """ffmpeg 抽音频（16k 单声道）"""
    cmd = [ffmpeg(), "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "pcm_s16le", out_wav]
    subprocess.run(cmd, capture_output=True, timeout=300)


def transcribe(video_path: str) -> str:
    from faster_whisper import WhisperModel

    video = Path(video_path).resolve()
    out_dir = video.parent / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{video.stem}.json"

    if json_path.exists():
        print(f"↻ 转录已存在: {json_path}", flush=True)
        return str(json_path)

    # 抽音频
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav = tmp.name
    print("🎧 抽取音频...", flush=True)
    extract_audio(str(video), wav)

    # 转写（small 模型，CPU int8）
    print("🎧 faster-whisper 转写中（small/int8）...", flush=True)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(wav, language="zh", beam_size=5)

    rows = []
    for seg in segments:
        rows.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
        })
        print(f"  [{seg.start:5.1f}-{seg.end:5.1f}] {seg.text.strip()}", flush=True)

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(wav).unlink(missing_ok=True)
    print(f"✓ 转录: {json_path}", flush=True)
    return str(json_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    transcribe(sys.argv[1])
