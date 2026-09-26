"""两条 15s one-take 无损拼接成 30s 成片（宝哥 2026-09-26 令：30 秒 = 两个 15s 拼接）

设计要点：
  · 两条各自走完整后期链（明快档裁剪 → 烧字幕 → BGM/SFX），**拼接放在最后一步** ——
    字幕已经烧进画面，拼接后时间轴天然正确，不需要重排字幕。
  · concat demuxer + `-c copy` 无损硬切（不重编码、不丢画质、切点零延迟）。
  · 拼接前 ffprobe 校验参数一致性（编码/分辨率/帧率/音频采样率/像素格式）——
    不一致时 concat demuxer 会静默出坏片（黑屏或音画错位），必须前置拦。
  · 需要重编码时加 --reencode（参数不一致时的兜底，用 libx264 CRF18 + AAC192k）。

用法：
  # 无损拼接（推荐，两条片子参数一致时）
  python tools/concat_takes.py out/approved/S30_1_zhaifeng_fx.mp4 out/approved/S30_2_tangping_fx.mp4

  # 指定输出名
  python tools/concat_takes.py a.mp4 b.mp4 -o out/approved/49_S30_30s.mp4

  # 只看参数不拼
  python tools/concat_takes.py a.mp4 b.mp4 --check
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 校验这些字段一致（不一致 → 拒绝无损拼接）
KEYS = {
    "codec_name": "视频编码",
    "width": "宽",
    "height": "高",
    "r_frame_rate": "帧率",
    "pix_fmt": "像素格式",
    "sample_rate": "音频采样率",
    "channels": "声道数",
}


def ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit(f"✗ ffprobe 失败：{path}\n{out.stderr}")
    data = json.loads(out.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    return {
        "path": path,
        "codec_name": v.get("codec_name", "?"),
        "width": v.get("width"),
        "height": v.get("height"),
        "r_frame_rate": v.get("r_frame_rate", "?"),
        "pix_fmt": v.get("pix_fmt", "?"),
        "sample_rate": a.get("sample_rate", "?"),
        "channels": a.get("channels", "?"),
        "duration": float(data["format"].get("duration", 0) or 0),
        "has_audio": bool(a),
    }


def compare(probes: list[dict]) -> list[str]:
    problems = []
    base = probes[0]
    for p in probes[1:]:
        for k, label in KEYS.items():
            if p[k] != base[k]:
                problems.append(f"{p['path'].name} 的{label} {p[k]} ≠ {base['path'].name} 的{base[k]}")
    for p in probes:
        if not p["has_audio"]:
            problems.append(f"{p['path'].name} 没有音轨 —— 拼接后那一段会静音")
    return problems


def reencode(paths: list[Path], out: Path) -> None:
    """兜底：参数不一致时统一重编码（CRF18 近无损 + AAC192k）"""
    inputs: list[str] = []
    for p in paths:
        inputs += ["-i", str(p)]
    n = len(paths)
    filt = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", filt,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def concat_copy(paths: list[Path], out: Path) -> None:
    """无损：concat demuxer + stream copy"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        for p in paths:
            fh.write(f"file '{p.resolve().as_posix()}'\n")
        listfile = Path(fh.name)
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-c", "copy", "-movflags", "+faststart", str(out),
        ]
        subprocess.run(cmd, check=True)
    finally:
        listfile.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+", help="按顺序拼接的视频（2 条 = 30s）")
    ap.add_argument("-o", "--out", default=None, help="输出路径（默认 out/approved/30s_concat_<日期>.mp4）")
    ap.add_argument("--check", action="store_true", help="只校验参数，不拼接")
    ap.add_argument("--reencode", action="store_true", help="强制重编码（参数不一致时的兜底）")
    args = ap.parse_args()

    paths = [(Path(v) if Path(v).is_absolute() else ROOT / v) for v in args.videos]
    for p in paths:
        if not p.exists():
            sys.exit(f"✗ 找不到 {p}")
    if shutil.which("ffprobe") is None:
        sys.exit("✗ 找不到 ffprobe（需要 ffmpeg 在 PATH 里）")

    probes = [ffprobe(p) for p in paths]
    print("参数体检：")
    for pr in probes:
        print(f"  {pr['path'].name}  {pr['width']}x{pr['height']} {pr['r_frame_rate']} "
              f"{pr['codec_name']}/{pr['pix_fmt']} 音{pr['sample_rate']}Hz×{pr['channels']} "
              f"{pr['duration']:.2f}s")
    total = sum(p["duration"] for p in probes)
    print(f"  合计时长：{total:.2f}s")

    problems = compare(probes)
    if problems:
        print("\n⚠ 参数不一致：")
        for x in problems:
            print(f"  · {x}")
        if not args.reencode:
            sys.exit("\n✗ 无损拼接会出坏片 → 加 --reencode 走兜底重编码，或先统一下两条片子的参数")
        print("\n→ --reencode：改用 filter_complex 重编码拼接")
    else:
        print("✓ 参数一致，可无损硬切")

    if args.check:
        return 0

    out = Path(args.out) if args.out else ROOT / "out" / "approved" / f"30s_concat_{__import__('datetime').date.today():%Y%m%d}.mp4"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n拼接中 → {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    if args.reencode or problems:
        reencode(paths, out)
    else:
        concat_copy(paths, out)

    final = ffprobe(out)
    print(f"✓ 完成：{final['duration']:.2f}s  {final['width']}x{final['height']}  "
          f"{out.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"  绝对路径：{out}")
    if abs(final["duration"] - total) > 1.0:
        print(f"⚠ 输出时长 {final['duration']:.2f}s 与预期 {total:.2f}s 差异 >1s，建议抽帧复核切点")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
