"""女主音色试听带生成：TTS 报号 + 候选真人样本拼接成一条 MP3（宝哥人耳选型）

用法：
  .venv/Scripts/python.exe tools/make_voice_audition.py             # 默认候选集
  .venv/Scripts/python.exe tools/make_voice_audition.py --out x.mp3

输出：assets/cast/voice/_audition_女主_<日期>.mp3（报号用另一把 TTS 嗓，避免和候选混淆）
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
FF = r"C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"
VOICE = ROOT / "assets/cast/voice"
TMP = VOICE / "_audition_tmp"
LABEL_VOICE = "zh-CN-XiaoxiaoNeural"   # 报号嗓（与候选明显区分）
CLIP_SEC = 4.5                          # 每个候选截取时长
GAP = 0.35                              # 条目间隔

# (报号文案, 样本相对路径, 备注)
CANDIDATES = [
    ("候选一", "real/r05_young_female.mp3", "当前用的·甜美青年女（你说不好听）"),
    ("候选二", "real/r07_nurse_female.mp3", "青年女·专业清爽"),
    ("候选三", "real/r10_female.mp3", "女·时尚亮一点"),
    ("候选四", "city_young_woman_26.mp3", "青年女·26岁"),
    ("候选五", "city_daughter_35.mp3", "轻熟女·35岁"),
    ("候选六", "real/p_yixi_3_1.mp3", "自然口语·播客女声"),
]


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} 失败: {(r.stderr or '')[-200:]}")


async def tts(text: str, out: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, LABEL_VOICE, rate="+15%").save(str(out))


def norm_clip(src: Path, out: Path, secs: float) -> None:
    """截取 + 统一响度（-16 LUFS），保证 A/B 比对公平"""
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-t", str(secs), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "2",
         "-c:a", "libmp3lame", "-b:a", "128k", str(out)])


def silence(out: Path, secs: float) -> None:
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"anullsrc=r=44100:cl=stereo", "-t", str(secs),
         "-c:a", "libmp3lame", "-b:a", "128k", str(out)])


def main() -> None:
    ap_out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    TMP.mkdir(parents=True, exist_ok=True)
    for f in TMP.glob("*.mp3"):
        f.unlink()

    parts: list[Path] = []
    gap = TMP / "gap.mp3"
    silence(gap, GAP)

    print("组装试听带：")
    for i, (label, rel, note) in enumerate(CANDIDATES, 1):
        src = VOICE / rel
        if not src.exists():
            print(f"  ✗ 缺样本 {rel}，跳过")
            continue
        lab = TMP / f"{i:02d}_label.mp3"
        asyncio.run(tts(f"{label}。", lab))
        clip = TMP / f"{i:02d}_clip.mp3"
        norm_clip(src, clip, CLIP_SEC)
        parts += [lab, clip, gap]
        print(f"  {label}  ← {rel}  ({note})")

    if not parts:
        print("✗ 没有可用候选")
        return

    lst = TMP / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    out = Path(ap_out) if ap_out else VOICE / f"_audition_女主_{datetime.now():%Y%m%d_%H%M}.mp3"
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c:a", "libmp3lame", "-b:a", "128k", str(out)])
    dur = subprocess.run([FF.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error",
                          "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout.strip()
    print(f"\n✓ 试听带：{out}  ({float(dur):.1f}s)")


if __name__ == "__main__":
    main()
