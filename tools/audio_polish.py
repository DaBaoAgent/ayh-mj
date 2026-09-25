"""音频润色 v2 — 去生硬 + BGM 铺底（闪避）+ 音效自动插入（2026-09-25 升级）

处理链：
  1) 轻混响 + loudnorm -16 LUFS（去"干声生硬"）
  2) BGM：--bgm auto 从宝哥免费音乐库随机选"轻快"类；侧链闪避（说话时 BGM 自动压低）
  3) 音效：--sfx 按台词时间轴自动插（？！句→叮；动作句→咻；打脸/结尾前→啪）

用法:
  python tools/audio_polish.py <视频> [--bgm auto|path] [--sfx] [--transcripts json] [--dry]
输出: <stemn>_polished.mp4
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

REVERB = "aecho=0.8:0.9:40|60:0.12|0.08"
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
VOICE_CHAIN = f"{REVERB},{LOUDNORM}"

BGM_LIB = Path("D:/BaiduSyncdisk/3 艾伦和艾薇/免费音乐")
BGM_PREFERRED = ["轻快", "清新", "爵士-片头"]
SFX_DIR = ROOT / "assets/sfx"

# 音效自动插入规则：(关键词, 音效文件名)
SFX_RULES = [
    ("？！", "ding.mp3"), ("?!", "ding.mp3"), ("?", "ding.mp3"), ("！", "ding.mp3"),
    ("走就走", "whoosh.mp3"), ("拎", "whoosh.mp3"), ("提", "whoosh.mp3"), ("往上走", "whoosh.mp3"),
    ("等等我", "whoosh.mp3"), ("上去", "whoosh.mp3"),
    ("修不动", "pop.mp3"), ("没白请", "pop.mp3"), ("换新", "pop.mp3"), ("坡", "pop.mp3"),
    ("听话", "ding.mp3"), ("点头", "ding.mp3"),
]


def pick_bgm() -> Path | None:
    """从宝哥音乐库随机选轻快类"""
    if not BGM_LIB.exists():
        return None
    for sub in BGM_PREFERRED:
        d = BGM_LIB / sub
        if d.exists():
            cands = [p for p in d.glob("*.mp3") if p.stat().st_size > 500_000]
            if cands:
                return random.choice(cands)
    cands = [p for p in BGM_LIB.glob("*.mp3") if p.stat().st_size > 500_000]
    return random.choice(cands) if cands else None


def sfx_points(tjson: Path) -> list[tuple[float, str]]:
    """从转写 json 找插入点"""
    if not tjson.exists():
        return []
    data = json.loads(tjson.read_text(encoding="utf-8"))
    if isinstance(data, list):
        segs = data
    else:
        segs = data.get("segments", [])
    pts: list[tuple[float, str]] = []
    used = set()
    for s in segs:
        text = (s.get("text") or "")
        start = float(s.get("start", 0))
        for kw, sfx in SFX_RULES:
            if kw in text and sfx not in used:
                used.add(sfx)
                pts.append((max(0.0, start - 0.08), sfx))
                break
    return pts[:5]


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    video = Path(args[0]).resolve()
    dry = "--dry" in args
    bgm_arg = args[args.index("--bgm") + 1] if "--bgm" in args else None
    do_sfx = "--sfx" in args
    tjson = Path(args[args.index("--transcripts") + 1]) if "--transcripts" in args else None
    out = video.with_name(video.stem.replace("_trim", "") + "_polished.mp4")

    bgm = None
    if bgm_arg:
        bgm = pick_bgm() if bgm_arg == "auto" else Path(bgm_arg)
        if bgm and not bgm.exists():
            bgm = None

    # ── 音效链 ──
    inputs = [ffmpeg(), "-y", "-i", str(video)]
    fc = []
    n = 1
    sfx_pts = sfx_points(tjson) if (do_sfx and tjson) else []
    for t, sfx in sfx_pts:
        f = SFX_DIR / sfx
        if not f.exists():
            continue
        inputs += ["-i", str(f)]
        fc.append(f"[{n}:a]adelay={int(t*1000)}|{int(t*1000)},volume=0.5[s{n}]")
        n += 1

    voice = f"[0:a]{VOICE_CHAIN}[v0]"
    fc.append(voice)
    mix_in = ["[v0]"] + [f"[s{i}]" for i in range(1, n)]

    if bgm:
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]
        # 侧链闪避：BGM 被语音压低
        fc.append(f"[{n}:a]volume=0.20[bg]")
        fc.append(f"[bg][v0]sidechaincompress=threshold=0.03:ratio=6:attack=80:release=350[bgd]")
        mix_in.append("[bgd]")

    fc.append(f"{''.join(mix_in)}amix=inputs={len(mix_in)}:duration=first:normalize=0[aout]")

    cmd = inputs + [
        "-filter_complex", ";".join(fc),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out),
    ]

    print(f"  bgm: {bgm.name if bgm else '(无)'} | sfx: {[s for _, s in sfx_pts]}", flush=True)
    if dry:
        print(" $", " ".join(cmd)[:300])
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = out.exists() and out.stat().st_size > 10000
    print(f"{'✓ 输出: ' + str(out) if ok else '✗ 失败: ' + r.stderr[-400:]}", flush=True)


if __name__ == "__main__":
    main()
