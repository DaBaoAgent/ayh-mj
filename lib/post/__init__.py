"""后期链统一层（Phase 9）：ASR、字幕时间、BGM、SFX、响度。

对外四件事：
  · `transcript`  —— 唯一 canonical 转写（一次 ASR，全链复用）；
  · `audio_director` —— BGM 元数据 + 按 StorySpec 选曲；
  · `sfx`         —— 动态音效放置（动作/反转/punchline/品牌 beat）；
  · `loudness`    —— 统一响度/真峰值检测与阈值。

`story_audio_brief(spec_doc)` 把一份 spec 里的 StorySpec 拆成 mood_curve / beat_map /
genre，供 make_15s / audio_polish 直接喂给 AudioDirector 与 SFX。
"""
from __future__ import annotations

from .audio_director import (
    BGM_META_FIELDS,
    GENRE_BGM_PROFILE,
    BgmTrack,
    infer_metadata,
    load_library,
    pick_bgm,
    select_bgm,
)
from .loudness import (
    LOUDNESS_BAND,
    LOUDNESS_TARGET,
    TRUE_PEAK_MAX,
    in_band,
    limiter_filter,
    master_for_mix,
    master_gain,
)
from .loudness import (
    issues as loudness_issues,
)
from .loudness import (
    measure as measure_loudness,
)
from .loudness import (
    summarize as summarize_loudness,
)
from .sfx import GENRE_SFX_POLICY, SFX_FILES, SfxHit, plan_sfx, policy_for, resolve_files
from .transcript import (
    CanonicalTranscript,
    Segment,
    Word,
    align_spans,
    build_rows,
    canonical_path,
    ensure_stub,
    write_srt,
)
from .transcript import (
    ensure as ensure_transcript,
)
from .transcript import (
    load as load_transcript,
)

__all__ = [
    "BGM_META_FIELDS", "CanonicalTranscript", "GENRE_BGM_PROFILE", "GENRE_SFX_POLICY",
    "LOUDNESS_BAND", "LOUDNESS_TARGET", "SFX_FILES", "TRUE_PEAK_MAX", "BgmTrack", "Segment",
    "SfxHit", "Word", "align_spans", "build_rows", "canonical_path", "ensure_stub",
    "ensure_transcript", "in_band", "infer_metadata", "load_library", "load_transcript",
    "limiter_filter", "loudness_issues", "master_for_mix", "master_gain", "measure_loudness",
    "pick_bgm", "plan_sfx",
    "policy_for", "resolve_files", "select_bgm", "story_audio_brief", "summarize_loudness",
    "write_srt",
]


def story_audio_brief(spec_doc: dict | None) -> dict:
    """从 spec 文档抽 (genre, mood_curve, beat_map, lines, shots) 给后期用。"""
    doc = spec_doc or {}
    story = doc.get("story_spec") or {}
    dna = (doc.get("creative") or {}).get("dna") or story.get("dna") or {}
    lines = [str(x.get("text") or "") if isinstance(x, dict) else str(x)
             for x in (story.get("lines") or [])]
    return {
        "uid": doc.get("job_uid") or story.get("uid") or "",
        "genre": str(dna.get("genre") or story.get("genre") or ""),
        "mood_curve": list(story.get("mood_curve") or []),
        "beat_map": list(story.get("beat_map") or []),
        "lines": [ln for ln in lines if ln.strip()],
        "shots": list(story.get("shots") or []),
        "dialogue_mode": str(dna.get("dialogue_mode") or ""),
    }
