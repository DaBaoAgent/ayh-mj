"""字幕生成：从镜头口播 + 时长生成 SRT

用法：
    from s5_compose.subtitle import make_srt
    make_srt([{seq, text, start, end}], "out.srt")
"""
from __future__ import annotations


def _fmt_time(seconds: float) -> str:
    """秒 → SRT 时间戳 00:00:00,000"""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_srt(cues: list[dict], out_path: str) -> str:
    """生成 SRT 文件

    cues: [{text, start, end}]（start/end 单位秒）
    """
    lines = []
    for i, cue in enumerate(cues, 1):
        text = cue.get("text", "").strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_fmt_time(cue['start'])} --> {_fmt_time(cue['end'])}")
        # 长句折行（每行最多 15 字，最多 2 行）
        lines.append(_wrap_text(text))
        lines.append("")

    content = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


def _wrap_text(text: str, max_chars: int = 14) -> str:
    """中文按字数折行（最多 2 行，超出部分续在第 2 行）"""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # 找中间标点断开
    puncts = "，。！？、；：,"
    mid = len(text) // 2
    best = -1
    for i in range(max(1, mid - 6), min(len(text) - 1, mid + 6)):
        if text[i] in puncts:
            best = i
            break
    if best > 0:
        line1, line2 = text[:best + 1], text[best + 1:]
    else:
        line1, line2 = text[:mid], text[mid:]
    if len(line2) > max_chars * 2:  # 太长就截断
        line2 = line2[:max_chars * 2 - 1] + "…"
    return f"{line1}\n{line2}"


def cues_from_tts(tts_results: list[dict]) -> list[dict]:
    """从 TTS 结果（各镜头音频时长）构建字幕时间轴"""
    cues = []
    t = 0.0
    for r in tts_results:
        d = r.get("duration", 0)
        if d <= 0 or not r.get("text"):
            continue
        cues.append({
            "text": r["text"],
            "start": t,
            "end": t + d,
        })
        t += d
    return cues
