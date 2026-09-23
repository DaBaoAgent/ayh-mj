"""模板链路成片烧字幕（抖音标配）

流程：gen_<uid>/final.mp4 → 转写（faster-whisper 系统Python）→ SRT → ffmpeg 烧录 → final_sub.mp4

用法：
    python s5_compose/burn_subtitles.py out/gen_t02_v1/final.mp4
    python s5_compose/burn_subtitles.py <视频> --srt <已有srt>   # 跳过转写
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import functools

from lib.tools import ffmpeg

# 转写用系统 Python（.venv 无 faster-whisper）
SYS_PYTHON = Path("C:/Users/xxx13/AppData/Local/Programs/Python/Python312/python.exe")

# 竖版字幕样式（1080 宽基准；白字黑边、底部居中、微软雅黑）
SUB_STYLE = ("FontName=Microsoft YaHei,FontSize=13,PrimaryColour=&HFFFFFF,"
             "OutlineColour=&H000000,BorderStyle=1,Outline=1.5,Shadow=0,"
             "Alignment=2,MarginV=28,Bold=1")


def _srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_segments(video: str) -> list[dict]:
    """调用系统 Python 的 transcribe_local.py，返回 segments"""
    video_p = Path(video).resolve()
    json_path = video_p.parent / "transcripts" / f"{video_p.stem}.json"
    if not json_path.exists():
        # 关键：清掉 PYTHONHOME/PYTHONPATH —— uv venv 里它们指向 uv 的 3.11，
        # 会让系统 Python 3.12 加载错版本 stdlib（SRE module mismatch）
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP")}
        r = subprocess.run([str(SYS_PYTHON), str(ROOT / "tools" / "transcribe_local.py"),
                            str(video_p)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900, env=env)
        if not json_path.exists():
            raise RuntimeError(f"转写失败: {r.stdout[-300:]} {r.stderr[-300:]}")
    return json.loads(json_path.read_text(encoding="utf-8"))


def _clean_for_match(s: str) -> str:
    """匹配用：去标点/空格/语气词"""
    import re as _re
    return _re.sub(r"[，。？！、\s,.?!]", "", s)


def _try_align(segments: list[dict], expected_lines: list[str]):
    """把已知台词对齐到转写段（修同音字）

    返回 (segments', texts') 或 None；segments' 可能与输入不同（时间轴合并后）。

    1) 条数相同 → 直接换文本
    2) 台词多于转写段（H3 连读短句）→ 合并台词到 n_seg 段
    3) 转写多于台词（H3 停顿切分）→ 合并转写段到 n_exp 段（时间轴重排）
    """
    from difflib import SequenceMatcher
    n_seg, n_exp = len(segments), len(expected_lines)
    if n_exp == n_seg:
        return segments, [line.strip() for line in expected_lines]
    if n_exp > n_seg and n_seg > 0:
        # 均匀分组合并（n_exp 句台词 → n_seg 段）
        groups: list[list[str]] = [[] for _ in range(n_seg)]
        for i, line in enumerate(expected_lines):
            groups[min(i * n_seg // n_exp, n_seg - 1)].append(line)
        merged = ["".join(g) for g in groups]
        sims = [SequenceMatcher(None, _clean_for_match(seg["text"]),
                                _clean_for_match(mg)).ratio()
                for seg, mg in zip(segments, merged, strict=False)]
        if sum(sims) / n_seg >= 0.35:
            print(f"✓ 台词合并校正（{n_exp}句→{n_seg}段，相似度{sum(sims)/n_seg:.2f}）", flush=True)
            return segments, merged
        print(f"⚠ 合并校正相似度过低（{sum(sims)/n_seg:.2f}），保留转写文本", flush=True)
    if n_seg > n_exp and n_exp > 0:
        # 转写段多于台词：DP 选最优"保序分组"（哪几段相邻合并），文本用台词
        clean_segs = [_clean_for_match(s["text"]) for s in segments]
        clean_exp = [_clean_for_match(line) for line in expected_lines]

        @functools.cache
        def _dp(i: int, j: int):
            """segs[i:] → 分成 exp[j:] 组的最小代价（代价 = Σ(1-相似度)）"""
            if j == n_exp:
                return (0.0, ()) if i == n_seg else (float("inf"), ())
            if (n_seg - i) < (n_exp - j):
                return (float("inf"), ())
            best = (float("inf"), ())
            max_k = n_seg - i - (n_exp - j - 1)
            for k in range(1, max_k + 1):
                text = "".join(clean_segs[i:i + k])
                sim = SequenceMatcher(None, text, clean_exp[j]).ratio()
                cost, rest = _dp(i + k, j + 1)
                total = (1 - sim) + cost
                if total < best[0]:
                    best = (total, ((i, i + k),) + rest)
            return best

        total_cost, bounds = _dp(0, 0)
        if bounds and total_cost != float("inf"):
            avg_sim = 1 - total_cost / n_exp
            if avg_sim >= 0.35:
                new_segs = [{
                    "start": segments[a]["start"],
                    "end": segments[b - 1]["end"],
                    "text": "".join(segments[x]["text"] for x in range(a, b)),
                } for a, b in bounds]
                print(f"✓ 转写合并校正（{n_seg}段→{n_exp}句，相似度{avg_sim:.2f}）", flush=True)
                return new_segs, [line.strip() for line in expected_lines]
            print(f"⚠ 转写合并校正相似度过低（{avg_sim:.2f}），保留转写文本", flush=True)
    return None


def _strip_punct(s: str) -> str:
    """去字幕标点（宝哥规则：字幕里不要标点符号）"""
    import re
    return re.sub(r"[，。？！、；：,.?!;:｜|]", "", s).strip()


def _cn_to_arabic(text: str) -> str:
    """字幕显示层：中文数字参数 → 阿拉伯数字（宝哥规则）

    只转数值参数（十三点八→13.8、十年→10年、二幺八→218），
    不影响 H3 生视频提示词（台词文本照旧——避免读错）。
    保护量词搭配：一键/一只手/一个人 等单字"一"不转。
    """
    import re
    d = {"零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
         "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "幺": "1"}

    def _int_cn(s: str) -> str:
        """中文整数 → 阿拉伯（十=10、十三=13、二十=20、二十五=25、两百=200 简化）"""
        if s == "十":
            return "10"
        m = re.fullmatch(r"([一二三四五六七八九])?十([一二三四五六七八九])?", s)
        if m:
            tens = d.get(m.group(1), "1") if m.group(1) else "1"
            ones = d.get(m.group(2), "") if m.group(2) else ""
            return str(int(tens) * 10 + int(ones or 0))
        return s

    # 1) X点Y 小数（十三点八 → 13.8；整数部分支持含"十"组合）
    def _dec(m):
        head = m.group(1)
        int_part = _int_cn(head) if "十" in head else d.get(head, head)
        return int_part + "." + "".join(d.get(c, c) for c in m.group(2))
    text = re.sub(r"([一二三四五六七八九]?十[一二三四五六七八九]?|[一二三四五六七八九零])点([零一二三四五六七八九]+)",
                  _dec, text)
    # 2) 含"十"的整数（十年→10年、二十→20、十三→13）
    text = re.sub(r"[一二三四五六七八九]?十[一二三四五六七八九]?", lambda m: _int_cn(m.group(0)), text)
    # 3) 含"幺"的号码串（二幺八 → 218）
    text = re.sub(r"[零一二三四五六七八九幺]*幺[零一二三四五六七八九幺]*",
                  lambda m: "".join(d.get(c, c) for c in m.group(0)), text)
    return text


def _split_natural(text: str, max_chars: int = 10) -> list[str]:
    """把一个句子拆成 ≤max_chars 的自然句行（去标点输出 + 参数数字化）

    规则（宝哥定 2026-09-23）：一次只显示一行、每行≤10字、尽量自然句、
    不带标点、参数用阿拉伯数字（十三点八→13.8）。
    """
    out = [s for s in (_strip_punct(x) for x in _split_raw(text, max_chars)) if s]
    return [_cn_to_arabic(s) for s in out]


def _split_raw(text: str, max_chars: int = 10) -> list[str]:
    """断句核心（保留标点用于判断，去标点在 _split_natural 统一处理）"""
    import re
    text = text.strip()
    if not text:
        return []
    # ｜/| 为双人台词分隔符 → 强制分句，各句独立处理
    if "｜" in text or "|" in text:
        out: list[str] = []
        for chunk in re.split(r"[｜|]", text):
            out.extend(_split_raw(chunk, max_chars))
        return out
    if len(text) <= max_chars:
        return [text]
    # 按标点切分（标点跟随前片段）
    pieces = re.findall(r"[^，。？！、；：,.?!;:｜|]+[，。？！、；：,.?!;:｜|]*", text) or [text]
    out = []
    cur = ""
    for piece in pieces:
        if len(cur) + len(piece) <= max_chars:
            cur += piece
        else:
            if cur:
                out.append(cur)
            # 片段自身超长 → 硬切
            p = piece
            while len(p) > max_chars:
                out.append(p[:max_chars])
                p = p[max_chars:]
            cur = p
    if cur:
        out.append(cur)
    return out


def _no_overlap(rows: list[tuple[float, float, str]], gap: float = 0.05) -> list[tuple[float, float, str]]:
    """防字幕重叠/相接（宝哥规则）：保证 start >= 上一条 end + gap"""
    out: list[tuple[float, float, str]] = []
    for start, end, text in rows:
        s, e = start, end
        if out and s < out[-1][1] + 0.0005:
            s = out[-1][1] + gap
        if e <= s:
            e = s + 0.2
        out.append((s, e, text))
    return out


def _explode_rows(segments: list[dict], texts: list[str] | None,
                  max_chars: int = 10) -> list[tuple[float, float, str]]:
    """把每条字幕拆成 ≤max_chars 的行，时间按字数比例分配

    返回 [(start, end, text), ...]，直接写 SRT。
    """
    rows: list[tuple[float, float, str]] = []
    for i, seg in enumerate(segments):
        text = texts[i].strip() if texts else seg["text"].strip()
        parts = _split_natural(text, max_chars)
        if not parts:
            continue
        if len(parts) == 1:
            rows.append((seg["start"], seg["end"], parts[0]))
            continue
        total = sum(len(p) for p in parts)
        t = seg["start"]
        dur = max(seg["end"] - seg["start"], 0.01)
        for p in parts:
            dt = dur * len(p) / total
            rows.append((t, min(t + dt, seg["end"]), p))
            t += dt
    return rows


def segments_to_srt(segments: list[dict], srt_path: Path,
                    expected_lines: list[str] = None, max_chars: int = 10) -> Path:
    """转写段落 → SRT；expected_lines 提供时做同音字校正（含连读/分段的合并对齐）

    字幕规则：一行≤max_chars 字、自然句成行、按字数比例分配时间轴。
    """
    texts = None
    if expected_lines:
        aligned = _try_align(segments, expected_lines)
        if aligned:
            segments, texts = aligned
    rows = _no_overlap(_explode_rows(segments, texts, max_chars=max_chars))
    lines = []
    for i, (start, end, text) in enumerate(rows, 1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(start)} --> {_srt_ts(end)}")
        lines.append(text)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def _probe_duration(video: Path) -> float:
    """ffmpeg 解析时长"""
    r = subprocess.run([ffmpeg(), "-i", str(video), "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


def shot_ranges_from_files(shots_dir: Path, n_shots: int) -> list[tuple[float, float]]:
    """从裁剪后的镜头文件推算拼接时间轴 [(t0, t1), ...]"""
    t = 0.0
    ranges = []
    for i in range(1, n_shots + 1):
        p = shots_dir / f"shot_{i:02d}.mp4"
        d = _probe_duration(p) if p.exists() else 0.0
        ranges.append((t, t + d))
        t += d
    return ranges


def segments_to_srt_by_shots(segments: list[dict], ranges: list[tuple[float, float]],
                             expected_lines: list[str], max_chars: int = 10) -> list[tuple[float, float, str]]:
    """按镜头时间轴精确对齐字幕（比 whisper 话轮分段准）

    - 每镜台词拆行（≤max_chars、去标点、数字化）
    - 镜内语音窗口：优先用落在该镜范围内的转写段起止；否则用整镜范围
    - 行时间：在语音窗口内按字数比例分配
    """
    rows: list[tuple[float, float, str]] = []
    for (t0, t1), line in zip(ranges, expected_lines, strict=False):
        if t1 <= t0:
            continue
        parts = _split_natural(line, max_chars)
        if not parts:
            continue
        segs = [s for s in segments if s.get("end", 0) > t0 + 0.05 and s.get("start", 0) < t1 - 0.05]
        if segs:
            win_start = max(t0, min(s["start"] for s in segs)) + 0.05
            win_end = min(t1, max(s["end"] for s in segs))
        else:
            win_start, win_end = t0 + 0.1, t1 - 0.1
        if win_end - win_start < 0.3:
            win_start, win_end = t0, t1
        total = sum(len(p) for p in parts)
        t = win_start
        for p in parts:
            dt = (win_end - win_start) * len(p) / total
            rows.append((t, min(t + dt, win_end), p))
            t += dt
    return _no_overlap(rows)


def burn_by_storyboard(video: str, shots_dir: Path, expected_lines: list[str],
                       suffix: str = "_sub") -> Path:
    """按镜头时间轴对齐烧字幕（字幕与对白精准匹配——宝哥规则）"""
    video_p = Path(video).resolve()
    n = len(expected_lines)
    ranges = shot_ranges_from_files(Path(shots_dir), n)
    segments = transcribe_segments(str(video_p))  # 仍转写（提供镜内语音窗口+日志）
    rows = segments_to_srt_by_shots(segments, ranges, expected_lines)
    srt_path = video_p.parent / f"{video_p.stem}.srt"
    lines = []
    for i, (start, end, text) in enumerate(rows, 1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(start)} --> {_srt_ts(end)}")
        lines.append(text)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ SRT（按镜头对齐）: {srt_path}（{len(rows)} 条 / {n} 镜）", flush=True)
    out = video_p.with_name(f"{video_p.stem}{suffix}.mp4")
    srt_arg = str(srt_path).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{srt_arg}':force_style='{SUB_STYLE}'"
    cmd = [ffmpeg(), "-y", "-i", str(video_p), "-vf", vf,
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
           "-c:a", "copy", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"烧字幕失败: {r.stderr[-400:]}")
    print(f"✓ 成片（带字幕）: {out}", flush=True)
    return out


def burn(video: str, srt: str = None, suffix: str = "_sub",
         expected_lines: list[str] = None) -> Path:
    """烧字幕，返回新文件路径

    expected_lines：分镜台词（已知文本）——用其替换转写文本修正同音字
    """
    video_p = Path(video).resolve()
    if srt:
        srt_path = Path(srt).resolve()
    else:
        segments = transcribe_segments(str(video_p))
        srt_path = video_p.parent / f"{video_p.stem}.srt"
        segments_to_srt(segments, srt_path, expected_lines=expected_lines)
        print(f"✓ SRT: {srt_path}（{len(segments)} 条）", flush=True)

    out = video_p.with_name(f"{video_p.stem}{suffix}.mp4")

    # Windows 路径转义：subtitles 滤镜需把盘符冒号转义
    srt_arg = str(srt_path).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{srt_arg}':force_style='{SUB_STYLE}'"

    cmd = [ffmpeg(), "-y", "-i", str(video_p), "-vf", vf,
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
           "-c:a", "copy", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"烧字幕失败: {r.stderr[-400:]}")
    print(f"✓ 成片（带字幕）: {out}", flush=True)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="成片烧字幕")
    parser.add_argument("video", help="视频路径")
    parser.add_argument("--srt", help="已有 SRT（跳过转写）")
    parser.add_argument("--suffix", default="_sub", help="输出文件后缀")
    args = parser.parse_args()
    burn(args.video, args.srt, args.suffix)
