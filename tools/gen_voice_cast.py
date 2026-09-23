"""音色定妆：为每个角色生成一条自我介绍视频 → 提取音色样本

原理：H3 首次生成时自然分配音色 → 该样本成为角色后续所有台词的克隆源（zm_u08 + ref_audio_0）
流程：zm_u08(角色图 + 介绍词对白) → 下载 → ffmpeg 提取音轨(去头尾静音) → <id>_voice.mp3
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from s4_generate.autodl_client import generate_video
from lib.tools import ffmpeg

LIB = ROOT / "assets" / "cast" / "library"
VOICE = ROOT / "assets" / "cast" / "voice"
VOICE.mkdir(parents=True, exist_ok=True)
TMP = ROOT / "out" / "voice_cast"

from gen_cast_city_ext import CAST_CITY_EXT  # noqa: E402

# 已有音色复用的核心角色对照（新角色列表见 CAST_CITY_EXT）


def voice_prompt(desc_line: str) -> str:
    return (
        "integrated_multimodal_description: [Shot 1] Live-action documentary close-up, static "
        "camera, natural daylight. The person from the reference image, keeping their exact face, "
        "hairstyle and clothing, looks slightly off-camera and speaks warmly at a natural pace: "
        "<d>[Chinese] " + desc_line + "</d> Their lips move in sync; mouth and eyes fully "
        "unobstructed. Only this person is in frame and only they speak.\n\n"
        "overall_soundscape: Quiet outdoor community ambience, the voice is clear and close.\n\n"
        "non_diegetic_music: N/A\n\n"
        "Hard constraints: render no watermarks, subtitles, captions, floating text, letters, "
        "numbers, stickers, logos or UI elements anywhere in frame; no background music."
    )


def make_voice_sample(cid: str, line: str) -> dict:
    sample = VOICE / f"{cid}.mp3"
    if sample.exists() and sample.stat().st_size > 10 * 1024:
        return {"id": cid, "status": "cached", "file": str(sample)}

    video = TMP / f"{cid}.mp4"
    TMP.mkdir(parents=True, exist_ok=True)
    if not video.exists() or video.stat().st_size < 100 * 1024:
        result = generate_video(
            prompt=voice_prompt(line),
            ref_images=[str(LIB / f"{cid}.png")],
            duration=5,
            resolution="768p竖",
            out_path=str(video),
            workflow="voice_clone",  # zm_u08（无 ref_audio，自然分配音色）
        )
    # 提取音轨（取中段 4.2s 去头尾）
    cmd = [ffmpeg(), "-y", "-ss", "0.5", "-t", "4.2", "-i", str(video),
           "-vn", "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "128k",
           str(sample)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {r.stderr[-200:]}")
    return {"id": cid, "status": "ok", "file": str(sample),
            "size_kb": sample.stat().st_size // 1024}


def main() -> int:
    print(f"🎤 音色定妆：{len(CAST_CITY_EXT)} 个城市角色", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(make_voice_sample, cid, line): cid
                   for cid, _, line in CAST_CITY_EXT}
        for f in as_completed(futures):
            cid = futures[f]
            try:
                r = f.result()
                results.append(r)
                print(f"  ✓ {cid}: {r['status']}", flush=True)
            except Exception as e:
                print(f"  ✗ {cid}: {str(e)[:150]}", flush=True)
                results.append({"id": cid, "status": "failed", "error": str(e)[:200]})

    ok = [r for r in results if r["status"] in ("ok", "cached")]
    print(f"\n完成 {len(ok)}/{len(CAST_CITY_EXT)}", flush=True)
    (TMP / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if len(ok) == len(CAST_CITY_EXT) else 1


if __name__ == "__main__":
    raise SystemExit(main())
