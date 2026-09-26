"""产品收尾镜 / 真景补镜：把生片里的某段剪出来接到已烧字幕段尾部（通用版）

用途（2026-09-26 实测得到的通用手法）：**提示词解决不了的事，用剪辑解决**——
只要某个形态在生片里出现过（宽景展示产品、某个动作、某个表情），就能把它剪出来当收尾镜/补镜。

典型场景：H3 无法在说词时持住宽景（只肯在宽景待 1-2 秒就推回特写），
         且宽景常落在「说话结束后的静音段」会被明快档裁剪剪掉 → 直接剪出来做产品收尾镜。

用法：
  .venv/Scripts/python.exe tools/append_wide_tail.py --dir out/gen_job_<uid> --start 4.5 --dur 2.0
  # 可选：--raw/--fx 显式指定文件；--mute 保留原声（默认静音，避免与正片台词/笑声重复）
  # 幂等：首次运行把原 fx 备份为 onetake_trim_fx_base.mp4，重复运行不会叠加

剪接用 -c copy（重编码参数对齐分段片，保证后续 concat 能无损接）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
FF = r"C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"
FP = FF.replace("ffmpeg.exe", "ffprobe.exe")
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "24",
       "-c:a", "aac", "-b:a", "128k", "-ar", "32000", "-ac", "2"]


def dur(p: Path) -> float:
    r = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="生成目录，如 out/gen_job_<uid>")
    ap.add_argument("--raw", default=None, help="生片（默认 <dir>/onetake.mp4）")
    ap.add_argument("--fx", default=None, help="已烧字幕段（默认 <dir>/onetake_trim_fx.mp4）")
    ap.add_argument("--start", type=float, default=4.5, help="补镜在生片里的起点（秒）")
    ap.add_argument("--dur", type=float, default=2.0, help="补镜时长（秒）")
    ap.add_argument("--keep-audio", action="store_true", help="保留原声（默认静音，防重复台词/笑声）")
    a = ap.parse_args()

    d = ROOT / a.dir
    raw = Path(a.raw) if a.raw else d / "onetake.mp4"
    fx = Path(a.fx) if a.fx else d / "onetake_trim_fx.mp4"
    if not raw.exists() or not fx.exists():
        sys.exit(f"✗ 缺文件：raw={raw.exists()} fx={fx.exists()}（先跑 post 生成 fx）")

    tail = d / "wide_tail.mp4"
    cmd = [FF, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(a.start), "-t", str(a.dur), "-i", str(raw)]
    if a.keep_audio:
        cmd += ["-map", "0:v", "-map", "0:a"]
    else:
        cmd += ["-f", "lavfi", "-t", str(a.dur), "-i", "anullsrc=r=32000:cl=stereo",
                "-map", "0:v", "-map", "1:a"]
    subprocess.run(cmd + ENC + [str(tail)], check=True)
    print(f"✓ 补镜 {tail.name} {dur(tail):.2f}s（{'保留原声' if a.keep_audio else '静音'}）")

    base = d / "onetake_trim_fx_base.mp4"
    if not base.exists():
        fx.rename(base)
        print(f"  已备份原段 → {base.name}")
    lst = d / "_concat_tail.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in (base, tail)), encoding="utf-8")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", str(fx)], check=True)
    print(f"✓ 装配完成 {fx.name} {dur(fx):.2f}s（正片 {dur(base):.2f}s + 补镜 {dur(tail):.2f}s）")


if __name__ == "__main__":
    main()
