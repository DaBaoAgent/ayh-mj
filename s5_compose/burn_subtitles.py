"""模板链路成片烧字幕（抖音标配）

流程：gen_<uid>/final.mp4 → 转写（faster-whisper 系统Python）→ SRT → ffmpeg 烧录 → final_sub.mp4

用法：
    python s5_compose/burn_subtitles.py out/gen_t02_v1/final.mp4
    python s5_compose/burn_subtitles.py <视频> --srt <已有srt>   # 跳过转写
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

# 转写用系统 Python（.venv 无 faster-whisper）
SYS_PYTHON = Path("C:/Users/xxx13/AppData/Local/Programs/Python/Python312/python.exe")

# 竖版字幕样式（1080 宽基准；白字黑边、底部居中、微软雅黑）
SUB_STYLE = ("FontName=Microsoft YaHei,FontSize=13,PrimaryColour=&HFFFFFF,"
             "OutlineColour=&H000000,BorderStyle=1,Outline=1.5,Shadow=0,"
             "Alignment=2,MarginV=28,Bold=1")


def _srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_segments(video: str) -> list[dict]:
    """调用系统 Python 的 transcribe_local.py，返回 segments"""
    video_p = Path(video).resolve()
    json_path = video_p.parent / "transcripts" / f"{video_p.stem}.json"
    if not json_path.exists():
        r = subprocess.run([str(SYS_PYTHON), str(ROOT / "tools" / "transcribe_local.py"),
                            str(video_p)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        if not json_path.exists():
            raise RuntimeError(f"转写失败: {r.stdout[-300:]} {r.stderr[-300:]}")
    return json.loads(json_path.read_text(encoding="utf-8"))


def segments_to_srt(segments: list[dict], srt_path: Path,
                    expected_lines: list[str] = None) -> Path:
    """转写段落 → SRT；expected_lines 提供时用已知台词替换文本（修同音字），时间轴不变"""
    lines = []
    use_expected = bool(expected_lines) and len(expected_lines) == len(segments)
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(seg['start'])} --> {_srt_ts(seg['end'])}")
        text = expected_lines[i - 1].strip() if use_expected else seg["text"]
        lines.append(text)
        lines.append("")
    if expected_lines and not use_expected:
        print(f"⚠ 台词条数({len(expected_lines)})≠转写条数({len(segments)})，用转写文本", flush=True)
    elif use_expected:
        print("✓ 已用已知台词校正字幕文本（修同音字）", flush=True)
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def burn(video: str, srt: str = None, suffix: str = "_sub",
         expected_lines: list[str] = None) -> Path:
    """烧字幕，返回新文件路径

    expected_lines：分镜台词（已知文本）——用其替换转写文本修正同音字
    """
    video_p = Path(video).resolve()
    if srt:
        srt_path = Path(srt).resolve()
    else:
        segments = transcribe_segments(str(video_p))
        srt_path = video_p.parent / f"{video_p.stem}.srt"
        segments_to_srt(segments, srt_path, expected_lines=expected_lines)
        print(f"✓ SRT: {srt_path}（{len(segments)} 条）", flush=True)

    out = video_p.with_name(f"{video_p.stem}{suffix}.mp4")

    # Windows 路径转义：subtitles 滤镜需把盘符冒号转义
    srt_arg = str(srt_path).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{srt_arg}':force_style='{SUB_STYLE}'"

    cmd = [ffmpeg(), "-y", "-i", str(video_p), "-vf", vf,
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
           "-c:a", "copy", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"烧字幕失败: {r.stderr[-400:]}")
    print(f"✓ 成片（带字幕）: {out}", flush=True)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="成片烧字幕")
    parser.add_argument("video", help="视频路径")
    parser.add_argument("--srt", help="已有 SRT（跳过转写）")
    parser.add_argument("--suffix", default="_sub", help="输出文件后缀")
    args = parser.parse_args()
    burn(args.video, args.srt, args.suffix)
