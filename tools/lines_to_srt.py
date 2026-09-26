"""字级对齐生成 SRT —— 用逐字时间戳把"台词句"钉到真实语音位置

为什么需要它：burn 自带的 _try_align 是**段级**（whisper VAD 段 ↔ 台词句）对齐，
段边界 ≠ 句边界时（转写段数=句数也会错位）精度不够。
本工具走**字符级**对齐：台词字符序列 ↔ 转写字符序列（带每字时间）→ 每句取首末字的真实时间。
再按 ≤max_chars 拆行（句内按字数比例），既准又满足"每行≤10字"。

用法：
  .venv/Scripts/python.exe tools/lines_to_srt.py <video> <lines.txt> <out.srt>
"""
from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent


def cjk(x: str) -> str:
    return re.sub(r"[^\u3400-\u9fff0-9A-Za-z]", "", x)


def build(video: Path, lines: list[str], max_chars: int = 10) -> list[tuple[float, float, str]]:
    from faster_whisper import WhisperModel
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(video), language="zh", vad_filter=True, word_timestamps=True)
    words: list[tuple[str, float, float]] = []
    for sg in segs:
        for w in (sg.words or []):
            for ch in cjk(w.word):
                words.append((ch, w.start, w.end))
    if not words:
        return []
    got = "".join(c for c, _, _ in words)
    exp = cjk("".join(lines))

    # 字符级对齐：exp 位置 → got 位置
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, exp, got, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[i1 + k] = j1 + k

    # 每句 → 真实起止（未对齐的位置用前后插值兜底）
    spans: list[tuple[float, float, str]] = []
    pos = 0
    for line in lines:
        n = len(cjk(line))
        idx = [mapping[i] for i in range(pos, pos + n) if i in mapping]
        if idx:
            a, b = words[min(idx)][1], words[max(idx)][2]
        else:                                   # 整句都对不上：借用前一句结束点，给 1.2s
            a = spans[-1][1] + 0.1 if spans else 0.0
            b = a + 1.2
        spans.append((a, b, line))
        pos += n

    # 句内拆行：优先用项目自带的自然断句（避免"…刹得住"+"吗"这种孤字行）
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "s5_compose"))
    from burn_subtitles import _split_natural
    rows: list[tuple[float, float, str]] = []
    for a, b, line in spans:
        try:
            chunks = _split_natural(line, max_chars)
        except Exception:
            chunks = []
        if not chunks:
            clean = re.sub(r"[，。？！、；：,.?!;:]", "", line)
            chunks = [clean[i:i + max_chars] for i in range(0, len(clean), max_chars)] or [clean]
        chunks = [c for c in chunks if c.strip()]
        total = sum(len(c) for c in chunks) or 1
        t = a
        for c in chunks:
            share = (b - a) * len(c) / total
            rows.append((round(t, 2), round(t + share, 2), c))
            t += share
    # 防重叠
    out = []
    for i, (a, b, txt) in enumerate(rows):
        if i and a < out[-1][1] + 0.03:
            a = out[-1][1] + 0.03
        if b <= a:
            b = a + 0.3
        out.append((a, b, txt))
    return out


def write_srt(rows, path: Path) -> None:
    def ts(t: float) -> str:
        h, r = divmod(t, 3600); m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((t % 1) * 1000):03d}"
    path.write_text("\n".join(f"{i+1}\n{ts(a)} --> {ts(b)}\n{t}\n"
                              for i, (a, b, t) in enumerate(rows)), encoding="utf-8")


if __name__ == "__main__":
    video, lines_f, srt_out = sys.argv[1], sys.argv[2], sys.argv[3]
    lines = [ln.strip() for ln in Path(lines_f).read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = build(Path(video), lines)
    write_srt(rows, Path(srt_out))
    print(f"✓ 字级对齐 SRT：{len(rows)} 行 → {srt_out}")
    for a, b, t in rows:
        print(f"   [{a:5.2f}-{b:5.2f}] {t}")
