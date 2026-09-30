"""本地转写（faster-whisper 直用）—— 全链**唯一**的 ASR 入口（Phase 9 任务 1/2）。

Phase 9 之前这里跑 `small` 出 segments 级转写，`lines_to_srt.py` 又用 `medium`
重跑一遍拿字级时间 —— 同一条视频两次推理、两份时间轴。现在只跑一次：

  · 模型/语言走 settings.asr（默认 medium，字级时间戳 word_timestamps=True）；
  · 结果落 `<视频目录>/transcripts/canonical.json`（segments + 每字 start/end + 源指纹）；
  · 命中缓存（源视频没变）直接复用，**不重推**；
  · 兼容产物 `transcripts/<stem>.json`（segments 级）由 canonical **派生**，供
    tools/check-take.mjs 等老消费者继续用，不是第二份事实源。

为什么不用 whisperx 的 alignment：中文对齐模型（wav2vec2-large-xlsr-53-chinese-zh-cn）
在 hf-mirror 拉不到 feature extractor → 对齐必失败。faster-whisper 自带的字级时间戳够用。

用法：
    python tools/transcribe_local.py <视频路径> [--force] [--model medium]
    → 产出 <视频目录>/transcripts/canonical.json（+ <stem>.json 兼容副本）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.post import transcript as T  # noqa: E402


def _settings_model() -> str:
    try:
        from lib.settings import get_settings

        return get_settings().asr.model or T.DEFAULT_MODEL
    except Exception:      # noqa: BLE001 - 设置不可用就退回默认模型
        return T.DEFAULT_MODEL


def transcribe(video_path: str, *, force: bool = False, model: str | None = None) -> str:
    """跑（或复用）canonical 转写 → 返回 canonical.json 路径。"""
    video = Path(video_path).resolve()
    workspace = video.parent
    model = model or _settings_model()

    tr, reused = T.ensure(video, workspace=workspace, model=model, force=force)
    if reused:
        print(f"↻ 复用 canonical 转写（未重推）: {T.canonical_path(workspace)}", flush=True)
    else:
        print(f"🎧 faster-whisper 转写（{tr.model}/{tr.language}，字级时间戳）...", flush=True)
    for seg in tr.segments:
        print(f"  [{seg.start:5.1f}-{seg.end:5.1f}] {seg.text}", flush=True)

    # 兼容副本：segments 级（老消费者 check-take.mjs 用），由 canonical 派生而非重推
    legacy = workspace / "transcripts" / f"{video.stem}.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps(
        [{"start": s.start, "end": s.end, "text": s.text} for s in tr.segments],
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ canonical: {T.canonical_path(workspace)}（{len(tr.segments)} 段 / "
          f"{tr.char_count} 字 / 指纹 {tr.fingerprint()}）", flush=True)
    return str(T.canonical_path(workspace))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    force = "--force" in sys.argv
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else None
    transcribe(args[0], force=force, model=model)
