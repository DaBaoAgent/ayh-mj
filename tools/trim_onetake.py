"""单条多镜头视频 · 静默节奏裁剪（onetake 专用）

宝哥标准（2026-09-24 定，节奏明快；同日批准为「明快档」= 默认档）：
  · 开头静默 → 保留 ≤0.15s（一打开就在动作里，尽快出声）
  · 结尾静默 → 保留 ≤0.15s（说完即止）
  · 镜头内/切换处停顿 ≥0.35s → 压到 0.20s；<0.35s 不动（保留自然呼吸）
原理：silencedetect 找静默段 → 视频+音频同步分段 → 裁掉多余静默 → concat。
（静默段内无人说话，裁剪不伤口型；轻缓运镜下画面连续性无感）

用法:
  python tools/trim_onetake.py <video.mp4>            # 只出报告（dry，不改文件）
  python tools/trim_onetake.py <video.mp4> --apply    # 执行（输出 <name>_trim.mp4）
可选覆盖: --trigger 0.45 --keep 0.28 （保守档参数）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg, ffprobe

HEAD_KEEP = 0.15
TAIL_KEEP = 0.15
MID_TRIGGER = 0.35
MID_KEEP = 0.20
SIL_DB = -35
SIL_D = 0.10
# Phase 9（任务 5）：裁剪后必须校验，局部失败不得静默跳过
MIN_PART_BYTES = 1024      # 一段 0.2s 纯色也可能只有几 KB —— 用「流完整」而不是字节数判断成功
MIN_OUT_BYTES = 1024     # 字节数只是最低底线；真成片由「流完整 + 时长吻合」判定


def _probe(path):
    """ffprobe 事实：时长 + 视频/音频流数量（探测失败留 0，不猜）。"""
    try:
        r = subprocess.run([ffprobe(), "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type", "-of", "json", str(path)],
                           capture_output=True, text=True, errors="replace")
        data = json.loads((r.stdout or "").strip() or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"duration": 0.0, "video": 0, "audio": 0}
    streams = data.get("streams") or []
    try:
        duration = float((data.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {"duration": round(duration, 3),
            "video": sum(1 for x in streams if x.get("codec_type") == "video"),
            "audio": sum(1 for x in streams if x.get("codec_type") == "audio")}


def _arg_val(name: str, default: float) -> float:
    """从命令行取 --name value（覆盖默认参数）"""
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return float(sys.argv[i + 1])
    return default


def probe_silences(video: Path):
    r = subprocess.run([ffmpeg(), "-i", str(video),
                        "-af", f"silencedetect=n={SIL_DB}dB:d={SIL_D}", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    t = r.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", t)
    total = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    segs, cur = [], None
    for ln in t.splitlines():
        m1 = re.search(r"silence_start:\s*(-?[\d.]+)", ln)
        if m1:
            cur = max(0.0, float(m1.group(1)))
        m2 = re.search(r"silence_end:\s*([\d.]+)", ln)
        if m2 is not None and cur is not None:
            segs.append((cur, float(m2.group(1))))
            cur = None
    if cur is not None:
        segs.append((cur, total))
    return total, segs


def plan_cuts(total: float, silences, mid_trigger: float = MID_TRIGGER,
              mid_keep: float = MID_KEEP):
    cuts = []
    for s, e in silences:
        L = e - s
        if s <= 0.05:
            if L > HEAD_KEEP:
                cuts.append((0.0, e - HEAD_KEEP, f"开头 {L:.2f}s → {HEAD_KEEP}s"))
        elif e >= total - 0.05:
            if L > TAIL_KEEP:
                cuts.append((s + TAIL_KEEP, total, f"结尾 {L:.2f}s → {TAIL_KEEP}s"))
        else:
            if mid_trigger <= L:
                c0, c1 = s + mid_keep / 2, e - mid_keep / 2
                if c1 > c0:
                    cuts.append((c0, c1, f"停顿 {s:.2f}-{e:.2f}（{L:.2f}s → {mid_keep}s）"))
    return cuts


def complement(total: float, cuts):
    keep, cur = [], 0.0
    for a, b, _ in cuts:
        if a > cur + 0.01:
            keep.append((cur, a))
        cur = max(cur, b)
    if cur < total - 0.01:
        keep.append((cur, total))
    return keep


def apply_keep(video: Path, keep, out: Path, *, tolerance: float | None = None) -> dict:
    """裁剪 → 拼回 → **校验**（任务 5）。返回 report（含 errors）；ok=False 即必须上抛。

    校验项：① 每段都真的产出（不允许静默丢段）② 输出存在且够大
            ③ 输出时长 ≈ 保留段总时长 ④ 视频/音频流完整（源有音频则输出也要有）。
    """
    report: dict = {"ok": False, "parts_expected": len(keep), "parts_produced": 0,
                    "expected_duration": round(sum(b - a for a, b in keep), 3),
                    "duration": 0.0, "video_streams": 0, "audio_streams": 0, "errors": []}
    if not keep:
        report["errors"].append("保留段为空，无可裁剪")
        return report
    src = _probe(video)
    tmp = Path(tempfile.mkdtemp(prefix="trim_onetake_"))
    parts, failed = [], []
    for i, (a, b) in enumerate(keep):
        p = tmp / f"seg_{i:02d}.mp4"
        r = subprocess.run([ffmpeg(), "-y", "-i", str(video), "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
                            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                            "-c:a", "aac", "-b:a", "128k", str(p)],
                           capture_output=True, text=True, errors="replace")
        ok_part = r.returncode == 0 and p.exists() and p.stat().st_size > MIN_PART_BYTES
        if ok_part:
            pr = _probe(p)
            ok_part = pr["video"] >= 1 and (src["audio"] < 1 or pr["audio"] >= 1)
        if ok_part:
            parts.append(p)
        else:
            failed.append(i)
    report["parts_produced"] = len(parts)
    if failed:
        report["errors"].append(f"局部 ffmpeg 失败，丢弃了 {len(failed)} 段：{failed}")
    if len(parts) != len(keep):
        report["errors"].append(f"产出段数 {len(parts)} ≠ 保留段数 {len(keep)}")
        return report

    lst = tmp / "list.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    r = subprocess.run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", str(out)], capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or not out.exists() or out.stat().st_size <= MIN_OUT_BYTES:
        report["errors"].append(f"拼接失败或输出过小：returncode={r.returncode}")
        return report

    probe = _probe(out)
    report.update({"duration": probe["duration"], "video_streams": probe["video"],
                   "audio_streams": probe["audio"]})
    if probe["video"] < 1:
        report["errors"].append("输出无视频流")
    if src["audio"] >= 1 and probe["audio"] < 1:
        report["errors"].append("源有音频流但输出无音频流")
    tol = tolerance if tolerance is not None else max(0.5, 0.05 * len(keep))
    if abs(probe["duration"] - report["expected_duration"]) > tol:
        report["errors"].append(
            f"输出时长 {probe['duration']:.2f}s 与保留时长 {report['expected_duration']:.2f}s "
            f"偏差超过 {tol:.2f}s")
    report["ok"] = not report["errors"]
    return report


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    video = Path(sys.argv[1]).resolve()
    apply = "--apply" in sys.argv
    trigger = _arg_val("--trigger", MID_TRIGGER)
    keep_target = _arg_val("--keep", MID_KEEP)
    total, segs = probe_silences(video)
    cuts = plan_cuts(total, segs, trigger, keep_target)
    print(f"视频: {video.name}  总长 {total:.2f}s  静默段 {len(segs)} 个")
    if not cuts:
        print("✓ 无需裁剪（已符合节奏标准）")
        return
    saved = sum(b - a for a, b, _ in cuts)
    for a, b, label in cuts:
        print(f"  裁 {a:6.2f}-{b:6.2f}  ({label})")
    print(f"→ 预计缩短 {saved:.2f}s：{total:.2f}s → {total - saved:.2f}s")
    if not apply:
        print("（dry 模式，加 --apply 执行）")
        return
    keep = complement(total, cuts)
    out = video.with_name(video.stem + "_trim.mp4")
    report = apply_keep(video, keep, out)
    if report["ok"]:
        print(f"✓ 输出: {out}（{report['parts_produced']}/{report['parts_expected']} 段 / "
              f"{report['duration']:.2f}s / v{report['video_streams']}·a{report['audio_streams']}）")
        return
    print("✗ 裁剪校验未通过（不静默出片）：")
    for err in report["errors"]:
        print("   -", err)
    out.unlink(missing_ok=True)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
