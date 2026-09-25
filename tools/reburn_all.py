"""批量重烧字幕（新青年体·不加粗·无标点·窄边框）— W1魔术 + B2脑洞10条

对每条：burn（新规范 _fx2）→ audio_polish（各自 BGM）→ 覆盖归档
文本/时间轴复用现有 onetake_trim.srt（ASS 层自动去标点）
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv/Scripts/python.exe")

BGM = json.loads((ROOT / "state/batch_brain2_bgm.json").read_text(encoding="utf-8"))["assignments"]

ITEMS = [
    ("W1_magic", "out/gen_job_W1_magic", "W1_一键魔术_20260925.mp4", "万恶之源.mp3"),
]
for uid, info in BGM.items():
    ITEMS.append((uid, f"out/gen_job_{uid}", f"B2_{uid.split('_')[1]}_{info['title']}_20260925.mp4", info["bgm"]))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


ok, fail = [], []
for uid, gdir, outname, bgm in ITEMS:
    g = ROOT / gdir
    trim = g / "onetake_trim.mp4"
    if not trim.exists():
        trim = g / "onetake.mp4"
    srt = g / "onetake_trim.srt"
    trj = g / "transcripts/onetake_trim.json"
    if not (trim.exists() and srt.exists()):
        print(f"✗ {uid}: 缺文件（trim={trim.exists()} srt={srt.exists()}）"); fail.append(uid); continue
    print(f"\n▶ {uid}")
    fx = g / "onetake_trim_fx2.mp4"
    r = run([PY, str(ROOT / "s5_compose/burn_subtitles.py"), str(trim), "--srt", str(srt), "--suffix", "_fx2"])
    if not fx.exists():
        print("  burn 失败:", (r.stderr or r.stdout)[-200:]); fail.append(uid); continue
    print("  burn ✓")
    r = run([PY, str(ROOT / "tools/audio_polish.py"), str(fx),
             "--bgm", str(ROOT / "assets/bgm_trending" / bgm), "--sfx",
             "--transcripts", str(trj)])
    final = g / "onetake_fx2_polished.mp4"
    if not final.exists():
        print("  polish 失败:", (r.stderr or r.stdout)[-200:]); fail.append(uid); continue
    print(f"  polish ✓（{bgm}）")
    shutil.copy(final, ROOT / "out/approved" / outname)
    print(f"  ✅ 归档 {outname}")
    ok.append(uid)

print(f"\n完成 {len(ok)}/{len(ITEMS)}｜失败: {fail}")
