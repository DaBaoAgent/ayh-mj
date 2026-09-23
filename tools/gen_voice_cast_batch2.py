"""音色定妆 · 第二批：第一组12城市角色 + 核心卡司elder/courier

补齐"20角色全有音色"缺口。
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
from gen_voice_cast import VOICE_HINT, voice_prompt

LIB = ROOT / "assets" / "cast" / "library"
CAST = ROOT / "assets" / "cast"
VOICE = CAST / "voice"
TMP = ROOT / "out" / "voice_cast"

# (id, 角色图, 介绍词, 音色类型)
CAST_BATCH2 = [
    ("city_grandpa_75", LIB / "city_grandpa_75.png", "我今年七十五，腿脚还利索。", "male_mature"),
    ("city_mom_45", LIB / "city_mom_45.png", "晚上给你们炖排骨，早点回来。", "female_adult"),
    ("city_daughter_35", LIB / "city_daughter_35.png", "妈，我明天陪你去复查。", "female_adult"),
    ("city_son_teen_16", LIB / "city_son_teen_16.png", "奶奶，这道题我会做！", "male_teen"),
    ("city_girl_8", LIB / "city_girl_8.png", "爸爸，我画了全家福！", "child_girl"),
    ("city_boy_10", LIB / "city_boy_10.png", "爷爷，教我下象棋呗。", "child_boy"),
    ("city_nurse_28", LIB / "city_nurse_28.png", "阿姨，血压正常，放心吧。", "female_adult"),
    ("city_neighbor_aunt_55", LIB / "city_neighbor_aunt_55.png", "老姐姐，今天广场舞去不去？", "female_mature"),
    ("city_young_man_30", LIB / "city_young_man_30.png", "师傅，五楼，麻烦您了。", "male_young"),
    ("city_young_woman_26", LIB / "city_young_woman_26.png", "这个颜色真好看，我要了。", "female_adult"),
    ("city_dad_50", LIB / "city_dad_50.png", "路上慢点，到了打电话。", "male_mature"),
    # 核心卡司
    ("elder", CAST / "elder_portrait.png", "唠一会儿，不着急走。", "male_mature"),
    ("courier", CAST / "courier_portrait.png", "您好，楼下取一下快递。", "male_young"),
]


def make_sample(cid: str, img: Path, line: str, vtype: str) -> dict:
    sample = VOICE / f"{cid}.mp3"
    if sample.exists() and sample.stat().st_size > 10 * 1024:
        return {"id": cid, "status": "cached"}
    if not Path(img).exists():
        return {"id": cid, "status": "skipped", "reason": f"缺角色图 {img.name}"}
    TMP.mkdir(parents=True, exist_ok=True)
    video = TMP / f"{cid}.mp4"
    if not video.exists() or video.stat().st_size < 100 * 1024:
        generate_video(prompt=voice_prompt(line, vtype), ref_images=[str(img)],
                       duration=5, resolution="768p竖", out_path=str(video),
                       workflow="voice_clone")
    cmd = [ffmpeg(), "-y", "-ss", "0.5", "-t", "4.2", "-i", str(video),
           "-vn", "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "128k", str(sample)]
    subprocess.run(cmd, check=True, capture_output=True)
    return {"id": cid, "status": "ok", "size_kb": sample.stat().st_size // 1024}


def main() -> int:
    todo = [j for j in CAST_BATCH2 if not (VOICE / f"{j[0]}.mp3").exists()]
    print(f"🎤 音色定妆第二批: 共 {len(CAST_BATCH2)} 个，需生成 {len(todo)} 个", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(make_sample, *j): j[0] for j in todo}
        for f in as_completed(futures):
            cid = futures[f]
            try:
                r = f.result()
                results.append(r)
                print(f"  ✓ {cid}: {r['status']}", flush=True)
            except Exception as e:
                print(f"  ✗ {cid}: {str(e)[:130]}", flush=True)
                results.append({"id": cid, "status": "failed", "error": str(e)[:200]})
    ok = [r for r in results if r["status"] in ("ok", "cached")]
    print(f"\n完成 {len(ok)}/{len(todo)}", flush=True)
    (TMP / "results_batch2.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
