"""TTS 配音：edge-tts 逐镜头生成语音

用法（模块）：
    from s5_compose.tts import gen_tts
    duration = gen_tts("要说的文字", "out.mp3")
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tools import ffprobe

DEFAULT_VOICE = "zh-CN-YunxiNeural"  # 云希（活力男声，适合软广）
DEFAULT_RATE = "+8%"


def gen_tts(text: str, out_path: str, voice: str = DEFAULT_VOICE,
            rate: str = DEFAULT_RATE) -> float:
    """生成 TTS 音频，返回时长（秒）"""
    import edge_tts

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    async def _gen():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(out))

    asyncio.run(_gen())

    return get_audio_duration(str(out))


def get_audio_duration(audio_path: str) -> float:
    """ffprobe 读取音频时长"""
    cmd = [
        ffprobe(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def gen_tts_for_shots(uid: str, shots: list[dict], out_dir: str) -> list[dict]:
    """为每个镜头生成 TTS（带断点续传）

    Returns: [{seq, audio_path, duration, text}]
    """
    results = []
    out_base = Path(out_dir)
    out_base.mkdir(parents=True, exist_ok=True)

    for shot in shots:
        seq = shot["seq"]
        text = shot.get("narration", "").strip()
        audio_path = out_base / f"tts_{seq:02d}.mp3"

        if not text:
            results.append({"seq": seq, "audio_path": None, "duration": 0, "text": ""})
            continue

        # 断点续传
        if audio_path.exists() and audio_path.stat().st_size > 1024:
            duration = get_audio_duration(str(audio_path))
            results.append({"seq": seq, "audio_path": str(audio_path),
                            "duration": duration, "text": text})
            print(f"    ↻ TTS{seq}: 已存在 {duration:.1f}s", flush=True)
            continue

        try:
            duration = gen_tts(text, str(audio_path))
            results.append({"seq": seq, "audio_path": str(audio_path),
                            "duration": duration, "text": text})
            print(f"    ✓ TTS{seq}: {duration:.1f}s ({len(text)}字)", flush=True)
        except Exception as e:
            print(f"    ✗ TTS{seq} 失败: {str(e)[:60]}", flush=True)
            results.append({"seq": seq, "audio_path": None, "duration": 0,
                            "text": text, "error": str(e)[:80]})

    return results


if __name__ == "__main__":
    # 自检
    d = gen_tts("这是一次配音自检，听到即成功。", "out/_tts_selftest.mp3")
    print(f"TTS 自检: {d:.1f}s")
