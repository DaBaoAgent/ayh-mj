"""字级对齐生成 SRT —— 时间**全部来自 canonical transcript**（Phase 9 任务 3/4）。

Phase 9 之前：本脚本自己用 `medium` + word_timestamps 再转写一次视频（第二次推理），
于是同一句台词的时间轴与转写链其它环节各算一份。现在不再推理：

  · canonical transcript 由 `tools/transcribe_local.py`（或任何已存在的 canonical）提供；
  · 本脚本只做「台词字符 ↔ 转写字符」对齐 + 自然断句拆行；
  · 若 canonical 不存在，会就地调用一次 `ensure()`（仍只推一次，并落 artifact 供后续复用）。

用法：
  .venv/Scripts/python.exe tools/lines_to_srt.py <video> <lines.txt> <out.srt>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.post import transcript as T  # noqa: E402
from lib.post.transcript import write_srt  # noqa: E402,F401  （回归测试从这里导入）


def build(video: Path, lines: list[str], max_chars: int = 10) -> list[tuple[float, float, str]]:
    """台词 → SRT 行；时间来自 canonical transcript（不重推 ASR）。"""
    video = Path(video).resolve()
    tr = T.load(video.parent)
    if tr is None or not T.matches_source(tr, video):
        tr, _ = T.ensure(video, workspace=video.parent)
    return T.build_rows(tr, lines, max_chars=max_chars)


if __name__ == "__main__":
    video, lines_f, srt_out = sys.argv[1], sys.argv[2], sys.argv[3]
    lines = [ln.strip() for ln in Path(lines_f).read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = build(Path(video), lines)
    write_srt(rows, Path(srt_out))
    print(f"✓ canonical 对齐 SRT：{len(rows)} 行 → {srt_out}")
    for a, b, t in rows:
        print(f"   [{a:5.2f}-{b:5.2f}] {t}")
