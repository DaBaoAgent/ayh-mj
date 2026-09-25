"""更新 real/INDEX.md — 追加播客采集样本清单（按来源分组）

用法: .venv/Scripts/python.exe tools/update_real_index.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REAL = ROOT / "assets/cast/voice/real"
STATE = ROOT / "state/podcast_harvest.json"


def dur_of(path: Path) -> float:
    import subprocess
    from lib.tools import ffprobe
    r = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main() -> None:
    import subprocess
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    p_files = sorted(REAL.glob("p_*.mp3"))
    if not p_files:
        print("无 p_*.mp3")
        return

    rows = []
    for f in p_files:
        tag = f.stem[2:].rsplit("_", 1)[0]
        info = state.get(tag, {})
        src = tag
        text = ""
        for m in info.get("made", []):
            if m.get("file") == f.name:
                src, text = m.get("from", tag), m.get("text", "")
        d = dur_of(f)
        rows.append((f.name, src, text[:38], d))

    idx = REAL / "INDEX.md"
    t = idx.read_text(encoding="utf-8")
    # 去掉旧「播客批量采集」段落再追加
    t = re.split(r"\n## 播客批量采集", t)[0]
    add = ["", f"## 播客批量采集（{len(rows)} 段）", "",
           "| 文件 | 来源 | 内容（转写首句） | 时长 |", "|---|---|---|---|"]
    for name, src, text, d in rows:
        add.append(f"| {name} | {src} | {text} | {d:.1f}s |")
    add += ["", "> 全部为真人自然口语（播客讲述）；适配角色以聆听为准"]
    idx.write_text(t + "\n".join(add) + "\n", encoding="utf-8")
    print(f"✓ INDEX.md 已更新：{len(rows)} 个播客样本")
    for name, src, text, d in rows:
        print(f"  {name} | {src} | {text[:30]}")


if __name__ == "__main__":
    main()
