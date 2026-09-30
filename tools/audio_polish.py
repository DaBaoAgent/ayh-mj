"""音频润色：人声链 + BGM 铺底 + 动态音效（Phase 9 统一后期）。

Phase 9 之前这里 `random.choice` 选 BGM、SFX_RULES 关键词命中就插、响度口径
与人声链各写一份。现在：

  · BGM 交给 `lib.post.audio_director`（按 StorySpec mood_curve/beat_map + 片型选曲，确定性）；
  · 音效交给 `lib.post.sfx.plan_sfx`（动作/反转/punchline/品牌 beat 动态放置 + 片型 policy）；
  · 人声 loudnorm 与成片响度检测共用 `lib.post.loudness`（一套阈值），混完即打印 LUFS/dBTP。

用法:
  python tools/audio_polish.py <视频> [--bgm auto|path] [--sfx] [--lines 台词.txt]
                              [--spec spec.json] [--genre G3] [--dry]
输出: <stem>_polished.mp4
"""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.post import loudness as L  # noqa: E402
from lib.post import transcript as T  # noqa: E402
from lib.post.audio_director import select_bgm  # noqa: E402
from lib.post.sfx import plan_sfx, resolve_files  # noqa: E402
from lib.tools import ffmpeg  # noqa: E402

REVERB = "aecho=0.8:0.9:40|60:0.12|0.08"
VOICE_CHAIN = REVERB                                    # 人声链只做混响；响度统一在混音总线
# 混音总线（任务 11）：先把「未过母线」的混音渲成 wav 实测（ebur128），
#   再由实测值算静态增益 → `volume=g,alimiter(与 TP 同源)`。
#   不信任 loudnorm 自报的 input_i（与落盘素材实测能差 8dB），只信对成片的 ebur128 读数。
MIX_MASTER_FALLBACK = f"{L.limiter_filter()}"
SFX_DIR = ROOT / "assets/sfx"
BGM_GAIN = 0.20


def _arg(args: list[str], name: str, default: str | None = None) -> str | None:
    return args[args.index(name) + 1] if name in args else default


def _brief(args: list[str]) -> dict:
    """从 --spec（有则用）或空的 brief 取 genre / mood_curve / beat_map / lines。"""
    from lib.post import story_audio_brief

    spec = _arg(args, "--spec")
    brief = {"genre": _arg(args, "--genre", "") or "", "mood_curve": [], "beat_map": [], "lines": []}
    if spec and Path(spec).is_file():
        with contextlib.suppress(OSError, ValueError):
            brief = story_audio_brief(json.loads(Path(spec).read_text(encoding="utf-8")))
    lines_f = _arg(args, "--lines")
    if lines_f and Path(lines_f).is_file():
        brief["lines"] = [ln.strip() for ln in Path(lines_f).read_text(encoding="utf-8").splitlines()
                          if ln.strip()]
    return brief


def _pick_bgm(args: list[str], brief: dict) -> Path | None:
    arg = _arg(args, "--bgm")
    if not arg:
        return None
    if arg != "auto":
        p = Path(arg)
        return p if p.is_file() else None
    track, rationale = select_bgm(brief.get("mood_curve"), brief.get("beat_map"),
                                  genre=str(brief.get("genre") or ""))
    if track is None:
        print(f"  ⚠ 曲库为空，跳过 BGM（{rationale.get('error')}）", flush=True)
        return None
    print(f"  🎵 AudioDirector 选曲：{track.name}（mood={track.mood} energy={track.energy} "
          f"genre={brief.get('genre')} score={rationale['score']}）", flush=True)
    return Path(track.path)


def _sfx_points(video: Path, brief: dict) -> list[tuple[float, Path, int]]:
    """canonical transcript + 台词 → 动态音效点（时间来自同一份 transcript）。"""
    lines = [str(x) for x in (brief.get("lines") or []) if str(x).strip()]
    if not lines:
        return []
    tr = T.load(video.parent)
    if tr is None:
        return []
    spans = T.align_spans(tr, lines)
    hits = plan_sfx(spans, lines, genre=str(brief.get("genre") or ""), story=brief)
    return [(at, path, hit.gain_db) for at, path, hit in resolve_files(hits, SFX_DIR)]


def _master_filter(mix_argv: list[str], graph: str, out: Path) -> str:
    """实测未过母线的**完整**混音图 → 返回母线过滤串（`volume=g,alimiter`）。"""
    wav = out.with_name(out.stem + "_premaster.wav")
    master, measured = L.master_for_mix(mix_argv, graph, wav)
    if wav.exists():
        wav.unlink()
    if measured.get("loudness_lufs") is None:
        print(f"  ⚠ 母线实测失败（{measured.get('error')}）：不增益，只限幅", flush=True)
        return MIX_MASTER_FALLBACK
    print(f"  母线实测：{L.summarize(measured)} → {master}", flush=True)
    return master


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    video = Path(args[0]).resolve()
    dry = "--dry" in args
    do_sfx = "--sfx" in args
    brief = _brief(args)
    out = video.with_name(video.stem.replace("_trim", "") + "_polished.mp4")

    bgm = _pick_bgm(args, brief)
    sfx = _sfx_points(video, brief) if do_sfx else []

    inputs = [ffmpeg(), "-y", "-i", str(video)]
    fc, n = [], 1
    for at, path, gain in sfx:
        inputs += ["-i", str(path)]
        ms = int(at * 1000)
        pre = "highpass=f=700," if path.name.startswith("ding") else ""
        fc.append(f"[{n}:a]{pre}volume={gain}dB,adelay={ms}|{ms}[s{n}]")
        n += 1

    fc.append(f"[0:a]{VOICE_CHAIN}[v0]")
    mix_in = ["[v0]"] + [f"[s{i}]" for i in range(1, n)]
    if bgm:
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]
        fc.append(f"[{n}:a]volume={BGM_GAIN}[bg]")
        fc.append("[bg][v0]sidechaincompress=threshold=0.03:ratio=6:attack=80:release=350[bgd]")
        mix_in.append("[bgd]")
    mix = f"{''.join(mix_in)}amix=inputs={len(mix_in)}:duration=first:normalize=0"
    print(f"  bgm: {bgm.name if bgm else '(无)'} | sfx: {[p.name for _, p, _ in sfx]}", flush=True)
    if dry:
        cmd = inputs + ["-filter_complex", ";".join(fc + [f"{mix},{MIX_MASTER_FALLBACK}[aout]"]),
                        "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", str(out)]
        print(" $", " ".join(cmd)[:300])
        return

    master = _master_filter(inputs, ";".join(fc + [mix]), out)
    cmd = inputs + ["-filter_complex", ";".join(fc + [f"{mix},{master}[aout]"]),
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = out.exists() and out.stat().st_size > 10000
    if not ok:
        print(f"✗ 失败: {r.stderr[-400:]}", flush=True)
        raise SystemExit(1)
    print(f"✓ 输出: {out}", flush=True)
    print(f"  统一响度检测：{L.summarize(L.measure(out))}", flush=True)


if __name__ == "__main__":
    main()
