"""成片装配：镜头拼接 + TTS配音 + 烧字幕

流程：
  1. 每个镜头：视频对齐到 TTS 时长（长了裁剪、短了冻结补帧）
  2. concat 拼接所有镜头（含音轨）
  3. 烧字幕（libass，微软雅黑）

用法：
    python s5_compose/merge.py --uid job_xxx
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import OUT_DIR
from lib.state import get_job, update_job
from lib.tools import ffmpeg, get_video_duration
from s5_compose.subtitle import cues_from_tts, make_srt
from s5_compose.tts import gen_tts_for_shots

TARGET_W, TARGET_H = 1080, 1920
# 字幕垂直位置（宝哥规则 2026-09-24）：底边落在画面「下方三分之一」处，验收后下调到 0.28
# ffmpeg subtitles 滤镜 PlayResY 固定 288 → MarginV = 288×比例（0.28 实测底边距底部 28.4%）
ASS_PLAY_RES_Y = 288
SUBTITLE_BOTTOM_RATIO = 0.25
SUBTITLE_MARGIN_V = round(ASS_PLAY_RES_Y * SUBTITLE_BOTTOM_RATIO)
SUBTITLE_STYLE = (
    "FontName=Microsoft YaHei,FontSize=15,PrimaryColour=&HFFFFFF&,"
    "OutlineColour=&H000000&,BorderStyle=1,Outline=2,Shadow=0,"
    f"Alignment=2,MarginV={SUBTITLE_MARGIN_V}"
)


def _run(cmd: list[str], cwd: str = None) -> subprocess.CompletedProcess:
    """跑 ffmpeg 命令（列表参数，无 shell 转义问题）"""
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=cwd)
    if result.returncode != 0:
        tail = (result.stderr or "")[-600:]
        raise RuntimeError(f"ffmpeg 失败(rc={result.returncode}): {tail}")
    return result


def fit_shot(shot_path: str, audio_path: str | None, audio_dur: float,
             out_path: str, workdir: str) -> str:
    """单镜头：视频对齐音频时长 + 统一规格（1080x1920 30fps）

    注意：ffmpeg 以 workdir 为 cwd 运行（避免 Windows 路径转义问题），
    所以所有输入输出路径先转绝对路径。
    """
    shot_path = str(Path(shot_path).resolve())
    out_path = str(Path(out_path).resolve())
    if audio_path:
        audio_path = str(Path(audio_path).resolve())

    video_dur = get_video_duration(shot_path)

    # 视频对齐到音频时长
    if audio_dur > 0:
        if audio_dur <= video_dur:
            vf_timing = f"trim=start=0:end={audio_dur},setpts=PTS-STARTPTS"
        else:
            pad = audio_dur - video_dur
            vf_timing = f"tpad=stop_mode=clone:stop_duration={pad},setpts=PTS-STARTPTS"
    else:
        vf_timing = "setpts=PTS-STARTPTS"

    # 统一规格：缩放到 1080x1920（保比补边）
    vf_scale = (f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
                f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30")

    vf = f"{vf_timing},{vf_scale}"

    cmd = [ffmpeg(), "-y", "-i", shot_path]
    if audio_path and audio_dur > 0:
        cmd += ["-i", audio_path]
        cmd += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    else:
        # 无配音镜头：静音轨
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]

    cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", out_path]

    _run(cmd, cwd=workdir)
    return out_path


def merge_job(uid: str) -> dict:
    """装配完整成片"""
    job = get_job(uid)
    if not job:
        raise ValueError(f"任务不存在: {uid}")

    # 确认镜头齐全
    shots_meta = json.loads(job["shots"]) if job.get("shots") else []
    ok_shots = [s for s in shots_meta if s.get("status") in ("ok", "cached")]

    storyboard = json.loads(job["storyboard"]) if job.get("storyboard") else {}
    sb_shots = {s["seq"]: s for s in storyboard.get("shots", [])}

    if not ok_shots:
        raise ValueError(f"任务 {uid} 没有已生成的镜头（先跑 s4_generate/batch_gen.py）")

    workdir = OUT_DIR / uid / "compose"
    workdir.mkdir(parents=True, exist_ok=True)

    # 按 seq 排序
    ok_shots.sort(key=lambda x: x["seq"])
    print(f"  🎞️ 装配 {uid}: {len(ok_shots)} 个镜头", flush=True)

    # 1. 逐镜头 TTS
    print("  1/3 TTS 配音...", flush=True)
    tts_shots = []
    for s in ok_shots:
        sb = sb_shots.get(s["seq"], {})
        tts_shots.append({"seq": s["seq"], "narration": sb.get("narration", "")})
    tts_results = gen_tts_for_shots(uid, tts_shots, str(workdir))

    # 2. 逐镜头对齐（视频贴合音频时长）
    print("  2/3 镜头对齐...", flush=True)
    seg_files = []
    for s in ok_shots:
        seq = s["seq"]
        shot_path = s.get("video_path") or str(OUT_DIR / uid / "shots" / f"shot_{seq:02d}.mp4")
        if not Path(shot_path).exists():
            print(f"    ⚠ 镜头{seq} 视频缺失，跳过", flush=True)
            continue
        tts = next((t for t in tts_results if t["seq"] == seq), None)
        audio_path = tts.get("audio_path") if tts else None
        audio_dur = (tts.get("duration") if tts else 0) or 0

        seg_path = str(workdir / f"seg_{seq:02d}.mp4")
        fit_shot(shot_path, audio_path, audio_dur, seg_path, str(workdir))
        dur = get_video_duration(seg_path)
        seg_files.append({"seq": seq, "path": seg_path, "duration": dur})
        print(f"    ✓ 镜头{seq}: {dur:.1f}s", flush=True)

    if not seg_files:
        raise ValueError("没有任何可用镜头")

    # 3. concat 拼接（流拷贝）
    print("  3/3 拼接 + 烧字幕...", flush=True)
    concat_list = workdir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{Path(f['path']).name}'" for f in seg_files),
        encoding="utf-8")
    str(workdir / "merged_raw.mp4")
    _run([ffmpeg(), "-y", "-f", "concat", "-safe", "0",
          "-i", concat_list.name, "-c", "copy", "merged_raw.mp4"], cwd=str(workdir))

    # 4. 字幕
    cues = cues_from_tts(tts_results)
    srt_path = workdir / "subs.srt"
    make_srt(cues, str(srt_path))

    # 5. 烧字幕 + 输出
    final_path = OUT_DIR / f"{uid}.mp4"
    _run([ffmpeg(), "-y", "-i", "merged_raw.mp4",
          "-vf", f"subtitles=subs.srt:force_style='{SUBTITLE_STYLE}'",
          "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
          "-c:a", "copy", str(final_path)],
         cwd=str(workdir))

    final_dur = get_video_duration(str(final_path))
    size_mb = final_path.stat().st_size / 1024 / 1024

    update_job(uid, status="ready",
               video_path=str(final_path), duration=final_dur)

    print(f"\n  ✓ 成片: {final_path}", flush=True)
    print(f"    {final_dur:.1f}s / {size_mb:.1f}MB", flush=True)

    return {"uid": uid, "video_path": str(final_path),
            "duration": final_dur, "size_mb": round(size_mb, 1)}


def run(uid: str) -> dict:
    return merge_job(uid)


def main() -> int:
    parser = argparse.ArgumentParser(description="成片装配")
    parser.add_argument("--uid", required=True, help="任务UID")
    args = parser.parse_args()

    result = merge_job(args.uid)
    return 0 if result.get("video_path") else 1


if __name__ == "__main__":
    raise SystemExit(main())
