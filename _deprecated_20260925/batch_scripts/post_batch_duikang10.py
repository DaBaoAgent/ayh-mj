"""短剧狗血10连 — 批量后期（trim → SRT → 烧字幕 → BGM/音效 → 归档）

结构同 post_batch_brain2.py；差异：台词/BGM 取自本批数据。
用法： .venv/Scripts/python.exe tools/post_batch_duikang10.py [uid ...]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from prep_duikang10 import SCRIPTS, TITLES  # noqa: E402

PY = str(ROOT / ".venv/Scripts/python.exe")
BGM = json.loads((ROOT / "docs/bgm分配-短剧狗血10连-20260925.json").read_text(encoding="utf-8"))["assignments"]
UIDS = [s["uid"] for s in SCRIPTS]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def main() -> None:
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    todo = only if only else UIDS
    for uid in todo:
        s = next(x for x in SCRIPTS if x["uid"] == uid)
        g = ROOT / f"out/gen_job_{uid}"
        src = g / "onetake.mp4"
        if not src.exists():
            print(f"✗ {uid} 缺文件，跳过"); continue
        print(f"\n{'=' * 50}\n▶ {uid} {TITLES[uid]}")

        # 1) trim（明快档）
        if not (g / "onetake_trim.mp4").exists():
            r = run([PY, str(ROOT / "tools/trim_onetake.py"), str(src), "--apply"])
            print("  trim:", (r.stdout or "").strip().splitlines()[-1] if r.stdout else (r.stderr or "")[-120:])
        if not (g / "onetake_trim.mp4").exists():
            shutil.copy(src, g / "onetake_trim.mp4")
            print("  trim: 无裁剪，已复制原片为 trim 版")

        # 2) 转写 trim 版（small；供 audio_polish 插音效用）
        tr_dir = g / "transcripts"
        tr_dir.mkdir(exist_ok=True)
        trj = tr_dir / "onetake_trim.json"
        if not trj.exists():
            run([PY, str(ROOT / "tools/transcribe_local.py"), str(g / "onetake_trim.mp4")], timeout=900)

        # 3) 台词文件（每行一句）
        lines_all = [t for sh in s["shots"] for _, t in sh["lines"]]
        lines_path = g / "onetake_lines.txt"
        lines_path.write_text("\n".join(lines_all), encoding="utf-8")

        # 4a) 字级对齐 SRT —— 逐字时间戳把每句钉到真实语音位置（精度高于段级 DP）
        srt_path = g / "onetake_words.srt"
        if not srt_path.exists():
            r = run([PY, str(ROOT / "tools/lines_to_srt.py"), str(g / "onetake_trim.mp4"),
                     str(lines_path), str(srt_path)])
            out = (r.stdout or "") + (r.stderr or "")
            print("  字级对齐:", "✓" if srt_path.exists() else out[-200:])

        # 4b) 烧字幕（新青年体/无标点/不加粗/动效）
        fx = g / "onetake_trim_fx.mp4"
        if not fx.exists():
            r = run([PY, str(ROOT / "s5_compose/burn_subtitles.py"), str(g / "onetake_trim.mp4"),
                     "--srt", str(srt_path), "--suffix", "_fx"])
            out = (r.stdout or "") + (r.stderr or "")
            print("  burn:", "✓" if fx.exists() else out[-250:])

        # 5) BGM + 音效
        bgm_file = ROOT / "assets/bgm_trending" / BGM[uid]["bgm"]
        final = g / "onetake_fx_polished.mp4"
        r = run([PY, str(ROOT / "tools/audio_polish.py"), str(fx),
                 "--bgm", str(bgm_file), "--sfx", "--transcripts", str(trj)])
        out = (r.stdout or "") + (r.stderr or "")
        print("  polish:", out.strip().splitlines()[-1] if out.strip() else "⚠️无输出")

        # 6) 归档 —— 直接用最终命名「<序号> 主体.mp4」（避免旧名与新名并存导致重复）
        if final.exists():
            of = ROOT / "state/approved_order.json"
            order = json.loads(of.read_text(encoding="utf-8")).get("order", {}) if of.exists() else {}
            seq = order.get(TITLES[uid])
            name = f"{seq} {TITLES[uid]}.mp4" if seq else f"D2_{uid.split('_')[1]}_{TITLES[uid]}_20260925.mp4"
            dst = ROOT / "out/approved" / name
            shutil.copy(final, dst)
            print(f"  ✅ 归档 {dst.name}")
        else:
            print(f"  ✗ {uid} 最终文件缺失")

    # 7) 统一改名（「<序号> <主体>.mp4」）+ 同步桌面
    r = run([PY, str(ROOT / "tools/rename_approved.py")])
    tail = (r.stdout or "").strip().splitlines()
    print("  改名:", tail[-1] if tail else (r.stderr or "")[-200:])
    print("\n全部处理完成")


if __name__ == "__main__":
    main()
