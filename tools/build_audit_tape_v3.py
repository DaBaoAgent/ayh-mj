"""真人样本审核带 v3 — 自动扫描 real/ 新采集样本 + TTS 报幕拼接

扫描 real/p_*.mp3（播客采集产物），按来源分组报幕（"故事FM，第1段"）
输出: out/voices/真人样本审核带v3.mp3
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg
from s5_compose.tts import gen_tts

REAL = ROOT / "assets/cast/voice/real"
WORK = ROOT / "out/voices/audit_v3"
WORK.mkdir(parents=True, exist_ok=True)
STATE = ROOT / "state/podcast_harvest.json"


def source_of(tag: str, state: dict) -> str:
    """从 state 找 tag 的来源名"""
    for k, v in state.items():
        if k == tag:
            for m in v.get("made", []):
                if m.get("from"):
                    return m["from"]
    return tag


def tts_retry(text: str, out: Path, tries: int = 4) -> bool:
    """TTS 带重试（edge-tts 偶发 NoAudioReceived）"""
    import time
    for i in range(tries):
        if out.exists() and out.stat().st_size > 1000:
            return True
        try:
            gen_tts(text, str(out), rate="+20%")
            if out.exists() and out.stat().st_size > 1000:
                return True
        except Exception as e:  # noqa: BLE001
            print(f"  tts retry {i+1}/{tries}: {type(e).__name__}", flush=True)
        time.sleep(1.5)
    return out.exists() and out.stat().st_size > 1000


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    samples = sorted(REAL.glob("p_*.mp3"))
    if not samples:
        print("✗ 没有 p_*.mp3 新样本")
        return

    # 汇总：来源 → [(文件, 文本)]
    groups: dict[str, list[tuple[Path, str]]] = {}
    for f in samples:
        tag = f.stem[2:]  # p_<tag>_<n>
        src = source_of(tag.rsplit("_", 1)[0], state)
        groups.setdefault(src, []).append((f, ""))

    # 顺序：先故事FM、一席，再老外，再其他
    order = ["故事FM", "一席", "白金时代", "银发世代", "老外你好", "人生杂叙(xm)"]
    seq = [g for g in order if g in groups] + [g for g in groups if g not in order]

    parts = []
    silence = WORK / "sil.mp3"
    subprocess.run([ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono", "-t", "0.6",
                    "-b:a", "96k", str(silence)], capture_output=True)

    n = 0
    for g in seq:
        items = sorted(groups[g], key=lambda x: x[0].name)
        for i, (f, _) in enumerate(items, 1):
            n += 1
            ann = WORK / f"a{n:03d}.mp3"
            tts_retry(f"{n}号，{g}，第{i}段", ann)
            s = WORK / f"s{n:03d}.mp3"
            subprocess.run([ffmpeg(), "-y", "-i", str(f), "-ar", "32000", "-ac", "1", "-b:a", "96k", str(s)],
                           capture_output=True)
            parts += [ann, s, silence]
            print(f"[{n}] {g} 第{i}段 ← {f.name}", flush=True)

    lst = WORK / "list.txt"
    lst.write_text("\n".join(f"file '{p.name}'" for p in parts), encoding="utf-8")
    out = ROOT / "out/voices/真人样本审核带v3.mp3"
    subprocess.run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-ar", "32000", "-ac", "1", "-b:a", "128k", str(out)], capture_output=True, cwd=str(WORK))
    if out.exists():
        dur = subprocess.run([ffmpeg().replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries",
                              "format=duration", "-of", "default=nw=1:nk=1", str(out)],
                             capture_output=True, text=True).stdout.strip()
        print(f"\n✓ {out}（{float(dur):.0f}s，{n} 段）")


if __name__ == "__main__":
    main()
