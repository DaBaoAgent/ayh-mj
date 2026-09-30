"""Canonical transcript —— 一条视频**只做一次** ASR，全链复用（Phase 9 必做 1/2/4）。

问题（Phase 9 之前）：
  · `tools/transcribe_local.py` 用 `small` 模型出一份 **segments 级** 转写；
  · `tools/lines_to_srt.py` 又用 `medium` + `word_timestamps` 重跑一遍，才拿到字级时间。
  同一条视频两次推理，字幕时间还来自第二次结果 —— 两条事实源。

现在：
  · 唯一入口 `ensure()`：workspace 里没有（或源视频变了）才跑一次 `medium` + 字级时间戳，
    写进 `transcripts/canonical.json`（含 segments + 每字 start/end + 源文件指纹）；
  · 之后所有步骤（一致性自检、字幕、SFX 定位）都 `load()` 这一份，永不重推；
  · `align_lines()` 从这里的时间轴算出每句真实起止 → `tools/lines_to_srt.py` 不再自己推理。

测试可注入 `transcriber=` 假实现（fake），真实实现对 faster-whisper 懒加载，
未安装时给出明确错误而不是 ImportError 炸链。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

CANONICAL_REL = "transcripts/canonical.json"
CJK_RE = re.compile(r"[^\u3400-\u9fff0-9A-Za-z]")
PUNCT_RE = re.compile(r"[，。？！、；：,.?!;:]")
DEFAULT_MODEL = "medium"


def cjk(text: str) -> str:
    return CJK_RE.sub("", text or "")


def workspace_uid(workspace: Path) -> str:
    """从 `out/gen_<uid>` 反推 uid（canonical 只依赖 workspace）。"""
    name = Path(workspace).name
    return name[4:] if name.startswith("gen_") else name


@dataclass
class Word:
    text: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"text": self.text, "start": round(self.start, 3), "end": round(self.end, 3)}

    @classmethod
    def from_dict(cls, d: dict) -> Word:
        return cls(str(d.get("text") or ""), float(d.get("start") or 0.0), float(d.get("end") or 0.0))


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3),
                "text": self.text, "words": [w.to_dict() for w in self.words]}

    @classmethod
    def from_dict(cls, d: dict) -> Segment:
        return cls(float(d.get("start") or 0.0), float(d.get("end") or 0.0),
                   str(d.get("text") or ""),
                   [Word.from_dict(w) for w in (d.get("words") or []) if isinstance(w, dict)])


@dataclass
class CanonicalTranscript:
    """一条视频的唯一转写事实源。"""

    uid: str
    source: str
    source_size: int = 0
    source_mtime: float = 0.0
    model: str = DEFAULT_MODEL
    language: str = "zh"
    created_at: str = ""
    engine: str = "faster-whisper"
    segments: list[Segment] = field(default_factory=list)

    # ── 派生量 ──────────────────────────────────────────────
    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def char_count(self) -> int:
        return len(cjk(self.text))

    @property
    def duration(self) -> float:
        return round(max((s.end for s in self.segments), default=0.0), 3)

    @property
    def has_word_timestamps(self) -> bool:
        return bool(self.words)

    def fingerprint(self) -> str:
        """内容指纹：同一份转写恒等（用于 artifact 去重/可复现）。"""
        blob = json.dumps([s.to_dict() for s in self.segments], ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]

    # ── 序列化 ──────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "schema": "canonical-transcript/1.0",
            "uid": self.uid, "source": self.source, "source_size": self.source_size,
            "source_mtime": round(self.source_mtime, 3), "model": self.model,
            "language": self.language, "engine": self.engine,
            "created_at": self.created_at or "", "duration": self.duration,
            "char_count": self.char_count, "word_count": self.word_count,
            "has_word_timestamps": self.has_word_timestamps,
            "fingerprint": self.fingerprint(),
            "text": self.text,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> CanonicalTranscript:
        return cls(
            uid=str(d.get("uid") or ""), source=str(d.get("source") or ""),
            source_size=int(d.get("source_size") or 0),
            source_mtime=float(d.get("source_mtime") or 0.0),
            model=str(d.get("model") or DEFAULT_MODEL), language=str(d.get("language") or "zh"),
            created_at=str(d.get("created_at") or ""), engine=str(d.get("engine") or "faster-whisper"),
            segments=[Segment.from_dict(s) for s in (d.get("segments") or []) if isinstance(s, dict)],
        )


def canonical_path(workspace: str | Path) -> Path:
    return Path(workspace) / CANONICAL_REL


def load(workspace: str | Path) -> CanonicalTranscript | None:
    """读 canonical artifact；不存在/损坏/版本不符都返回 None（不猜）。"""
    path = canonical_path(workspace)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("segments"):
        return None
    return CanonicalTranscript.from_dict(data)


def matches_source(tr: CanonicalTranscript, video: str | Path) -> bool:
    """canonical 是否就是这条视频转出来的（路径 + 大小 + mtime 三重指纹）。"""
    p = Path(video)
    if not p.is_file():
        return False
    try:
        st = p.stat()
    except OSError:
        return False
    same_path = Path(tr.source).resolve() == p.resolve() if tr.source else False
    return bool(same_path and tr.source_size == st.st_size and abs(tr.source_mtime - st.st_mtime) < 1.0)


# ── 真实转写（懒加载 faster-whisper）──────────────────────────────
def _extract_audio(video: str, out_wav: str) -> None:
    from ..tools import ffmpeg

    cmd = [ffmpeg(), "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "pcm_s16le", out_wav]
    subprocess.run(cmd, capture_output=True, timeout=600)      # noqa: PLW1510


def transcribe_real(video: str | Path, *, model: str = DEFAULT_MODEL, language: str = "zh",
                    device: str = "cpu", compute_type: str = "int8") -> tuple[list[Segment], dict]:
    """真跑一次 ASR（字级时间戳）→ (segments, info)。未装 faster-whisper 时抛 RuntimeError。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:      # pragma: no cover - 依赖可选
        raise RuntimeError(
            "faster-whisper 未安装：pip install 'faster-whisper>=1.0.0'（pyproject [asr] 可选依赖）"
        ) from exc

    video = str(Path(video).resolve())
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav = tmp.name
    try:
        _extract_audio(video, wav)
        wm = WhisperModel(model, device=device, compute_type=compute_type)
        segs, info = wm.transcribe(wav, language=language, beam_size=5,
                                   vad_filter=True, word_timestamps=True)
        out: list[Segment] = []
        for sg in segs:
            words = [Word(text=str(w.word).strip(), start=float(w.start), end=float(w.end))
                     for w in (sg.words or [])]
            out.append(Segment(start=float(sg.start), end=float(sg.end),
                               text=str(sg.text).strip(), words=words))
    finally:
        Path(wav).unlink(missing_ok=True)
    meta = {"model": model, "language": getattr(info, "language", language) or language,
            "duration": float(getattr(info, "duration", 0.0) or 0.0)}
    return out, meta


def save(workspace: str | Path, tr: CanonicalTranscript) -> Path:
    path = canonical_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tr.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def ensure(video: str | Path, *, workspace: str | Path, uid: str | None = None,
           transcriber=None, model: str = DEFAULT_MODEL, language: str = "zh",
           force: bool = False) -> tuple[CanonicalTranscript, bool]:
    """拿（或产生）canonical transcript → (transcript, reused)。

    `reused=True` 表示命中缓存、**没有**再跑推理（任务 1/2/4 的硬指标）。
    `transcriber` 可注入：签名 `(video) -> (segments, meta)`（测试用 fake，0 依赖）。
    """
    video = Path(video)
    workspace = Path(workspace)
    uid = uid or workspace_uid(workspace)

    cached = None if force else load(workspace)
    if cached is not None and matches_source(cached, video):
        return cached, True

    fn = transcriber or (lambda v: transcribe_real(v, model=model, language=language))
    segments, meta = fn(video)
    st = video.stat() if video.is_file() else None
    tr = CanonicalTranscript(
        uid=uid, source=str(video.resolve()), source_size=(st.st_size if st else 0),
        source_mtime=(st.st_mtime if st else 0.0),
        model=str(meta.get("model") or model), language=str(meta.get("language") or language),
        created_at=datetime.now().isoformat(timespec="seconds"), segments=list(segments),
    )
    save(workspace, tr)
    return tr, False


def ensure_stub(video: str | Path, *, workspace: str | Path, uid: str | None = None) -> CanonicalTranscript:
    """无 ASR 依赖时，从既有的 `transcripts/<stem>.json`（segments 级）兜底成 canonical。

    Phase 9 的口径：**能复用就复用**。老产线留下的 segments json 若已在，就直接升级为
    canonical（无字级时间），而不是再跑一次 medium。文件不存在 → 抛 FileNotFoundError。
    """
    video = Path(video)
    workspace = Path(workspace)
    legacy = video.parent / "transcripts" / f"{video.stem}.json"
    raw = json.loads(legacy.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else (raw.get("segments") or [])
    segments = [Segment(start=float(r.get("start") or 0.0), end=float(r.get("end") or 0.0),
                        text=str(r.get("text") or "").strip())
                for r in rows if isinstance(r, dict)]
    return CanonicalTranscript(uid=uid or workspace_uid(workspace), source=str(video.resolve()),
                               created_at=datetime.now().isoformat(timespec="seconds"),
                               model="legacy-segments", engine="legacy",
                               segments=segments)


# ── 对齐：canonical 时间轴 → 每句真实起止 ─────────────────────────
def _char_stream(tr: CanonicalTranscript) -> list[tuple[str, float, float]]:
    """把字级时间戳摊平成 [(汉字, start, end)]；没有字级时间就用 segments 均分插值。"""
    out: list[tuple[str, float, float]] = []
    if tr.has_word_timestamps:
        for w in tr.words:
            for ch in cjk(w.text):
                out.append((ch, w.start, w.end))
        return out
    for seg in tr.segments:
        chars = list(cjk(seg.text))
        if not chars:
            continue
        span = max(0.0, seg.end - seg.start) / len(chars)
        for i, ch in enumerate(chars):
            out.append((ch, seg.start + i * span, seg.start + (i + 1) * span))
    return out


def align_spans(tr: CanonicalTranscript, lines: list[str]) -> list[tuple[float, float]]:
    """每句台词 → (start, end)，时间全部来自 canonical。对不上的句子用前后插值兜底。"""
    if not lines:
        return []
    stream = _char_stream(tr)
    spans: list[tuple[float, float]] = []
    if not stream:
        # 完全无转写：按字符比例铺在总时长上（仍是同一份 transcript 的时长）
        total = tr.duration or 0.0
        weights = [max(1, len(cjk(ln))) for ln in lines]
        wsum = sum(weights) or 1
        t = 0.0
        for w in weights:
            share = total * w / wsum
            spans.append((round(t, 3), round(t + share, 3)))
            t += share
        return spans

    words = [(c, a, b) for c, a, b in stream]
    got = "".join(c for c, _, _ in words)
    exp = cjk("".join(lines))
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, _j2 in SequenceMatcher(None, exp, got, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[i1 + k] = j1 + k

    pos = 0
    for line in lines:
        n = len(cjk(line))
        idx = [mapping[i] for i in range(pos, pos + n) if i in mapping]
        if idx:
            a, b = words[min(idx)][1], words[max(idx)][2]
        else:
            a = spans[-1][1] + 0.1 if spans else 0.0
            b = a + 1.2
        spans.append((round(a, 3), round(max(b, a + 0.3), 3)))
        pos += n
    return spans


def split_line(text: str, max_chars: int) -> list[str]:
    """句内拆行：优先项目自带自然断句（避免孤字行），失败退回标点清洗 + 定长切。"""
    try:
        import sys

        root = Path(__file__).resolve().parent.parent.parent
        if str(root / "s5_compose") not in sys.path:
            sys.path.insert(0, str(root / "s5_compose"))
        from burn_subtitles import _split_natural

        chunks = _split_natural(text, max_chars)
    except Exception:      # noqa: BLE001 - 断句纯粹是优化，失败要能降级
        chunks = []
    if not chunks:
        clean = PUNCT_RE.sub("", text or "")
        chunks = [clean[i:i + max_chars] for i in range(0, len(clean), max_chars)] or [clean]
    return [c for c in chunks if c.strip()]


def rows_from_spans(spans: list[tuple[float, float]], lines: list[str], *,
                    max_chars: int = 10, gap: float = 0.03) -> list[tuple[float, float, str]]:
    """每句按字数比例分给拆行后的字幕行 → (start, end, text)，并保证不重叠。"""
    rows: list[tuple[float, float, str]] = []
    for (a, b), line in zip(spans, lines, strict=False):
        chunks = split_line(line, max_chars)
        total = sum(len(c) for c in chunks) or 1
        t = a
        for c in chunks:
            share = (b - a) * len(c) / total
            rows.append((round(t, 3), round(t + share, 3), c))
            t += share
    out: list[tuple[float, float, str]] = []
    for i, (a, b, txt) in enumerate(rows):
        a2, b2 = a, b
        if i and a2 < out[-1][1] + gap:
            a2 = round(out[-1][1] + gap, 3)
        if b2 <= a2:
            b2 = round(a2 + 0.3, 3)
        out.append((a2, b2, txt))
    return out


def build_rows(tr: CanonicalTranscript, lines: list[str], *, max_chars: int = 10) -> list[tuple[float, float, str]]:
    """canonical → SRT 行（全链唯一字幕时间来源，任务 4）。"""
    return rows_from_spans(align_spans(tr, lines), lines, max_chars=max_chars)


def write_srt(rows, path: str | Path) -> None:
    """写 SRT（时间格式回归由 tests/unit/test_subtitle_srt.py 守住）。"""
    def ts(t: float) -> str:
        h, r = divmod(t, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((t % 1) * 1000)):03d}"

    Path(path).write_text("\n".join(f"{i + 1}\n{ts(a)} --> {ts(b)}\n{t}\n"
                                    for i, (a, b, t) in enumerate(rows)), encoding="utf-8")
