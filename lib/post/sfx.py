"""SFX 动态放置 —— 由动作/反转/punchline/品牌 beat 触发（Phase 9 必做 9/10）。

Phase 9 之前：`tools/make_15s.py` 的 `SFX_PLAN` 把音效**钉死在第 4/5/7/8 句**
（赌约 ding / 崩溃 whoosh / 兑现 pop / 品牌 pop）—— 不管片型、不管剧情，四条片子
听起来一模一样，情感片也被强塞 ding/whoosh/pop。

现在：从句子内容 + StorySpec `beat_map` 里**动态**找触发点，并按片型 policy 收敛密度：
  · 动作词   → whoosh
  · 反转/转折 → whoosh（riser）
  · punchline / 兑现打脸 → pop
  · 品牌 beat → pop
  · 疑问/惊讶 → ding
片型政策（任务 10）：Vlog 自然（≤1）、魔性广告高密度（≤5）、情感片**零音效**。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

SFX_FILES = {"ding": "ding.mp3", "whoosh": "whoosh.mp3", "pop": "pop.mp3", "beep": "beep_device.wav"}

ACTION_WORDS = ("走就走", "拎", "提", "推", "拉", "爬", "摔", "丢", "冲", "跑", "抖",
                "抬", "扛", "拧", "按", "踩", "翻", "转", "换", "装", "试")
REVERSAL_WORDS = ("其实", "结果", "没想到", "谁知", "反转", "原来", "突然", "竟然", "反而")
PAYOFF_WORDS = ("打脸", "兑现", "真香", "厉害", "服了", "值了", "没白请", "赌", "赌约", "认输", "果然")
BRAND_WORDS = ("爱优护", "轻便侠", "轻捷侠")
QUESTION_MARKS = ("？", "?", "！", "!", "居然", "竟然")

# 片型 → SFX policy（density 供文档/测试直读；max 是硬上限）
GENRE_SFX_POLICY: dict[str, dict] = {
    "G1": {"density": "low", "max": 1, "allow": ("pop",)},
    "G2": {"density": "high", "max": 4, "allow": ("whoosh", "pop", "ding")},
    "G3": {"density": "high", "max": 5, "allow": ("ding", "whoosh", "pop")},
    "G4": {"density": "medium", "max": 3, "allow": ("ding", "pop", "whoosh")},
    "G5": {"density": "none", "max": 0, "allow": ()},
    "G6": {"density": "low", "max": 1, "allow": ("pop",)},
    "G7": {"density": "low", "max": 1, "allow": ("pop",)},
    "G8": {"density": "high", "max": 4, "allow": ("whoosh", "pop", "ding")},
    "G9": {"density": "medium", "max": 2, "allow": ("whoosh", "pop")},
    "G10": {"density": "medium", "max": 2, "allow": ("pop", "whoosh")},
}
DEFAULT_POLICY = {"density": "low", "max": 1, "allow": ("pop",)}

# 同类触发同时命中时的优先序（品牌/兑现 > 反转 > 动作 > 疑问）
_PRIORITY = {"brand": 5, "punchline": 4, "reversal": 3, "action": 2, "question": 1}

# 音效 bed 电平：素材本身只 -24dBTP 左右，抬电平必须**按素材实测峰值**算，
# 不能拍一个 +26dB 的常数（抬过头 → 混音峰值全由音效支配 → 母线不得不压 8dB，
# 成片反而更轻、动态也被毁）。`_GAIN_DB` 只在量不到素材时兜底。
SFX_BED_PEAK = -12.0                      # 音效 bed 真峰值目标（dBTP）
_GAIN_DB = {"ding": 13, "whoosh": 13, "pop": 12, "beep": 13}
_PEAK_CACHE: dict[tuple[str, int, int], float | None] = {}


def asset_peak_db(path: str | Path) -> float | None:
    """素材真峰值（dBTP），按 (路径, size, mtime) 缓存；量不到返回 None。"""
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None
    key = (str(p), st.st_size, int(st.st_mtime))
    if key not in _PEAK_CACHE:
        from .loudness import measure

        _PEAK_CACHE[key] = measure(p).get("true_peak_db")
    return _PEAK_CACHE[key]


def asset_gain_db(path: str | Path, *, target_peak: float = SFX_BED_PEAK) -> int | None:
    """把素材抬到 bed 目标峰值所需增益（dB，整数）；量不到峰值返回 None。"""
    peak = asset_peak_db(path)
    if peak is None:
        return None
    return int(round(max(-24.0, min(24.0, float(target_peak) - float(peak)))))


@dataclass
class SfxHit:
    at: float
    file: str
    kind: str
    reason: str
    trigger: str = "action"
    beat: str = ""
    gain_db: int = 20

    def to_dict(self) -> dict:
        return {"at": round(self.at, 3), "file": self.file, "kind": self.kind,
                "reason": self.reason, "trigger": self.trigger, "beat": self.beat,
                "gain_db": self.gain_db}


def policy_for(genre: str) -> dict:
    return GENRE_SFX_POLICY.get(genre, DEFAULT_POLICY)


def _triggers(text: str, *, is_last: bool, beat: str) -> list[tuple[str, str, str]]:
    """一句台词能触发哪几类音效 → [(kind, reason, trigger)]，按优先序排列。"""
    hits: list[tuple[str, str, str]] = []
    if any(w in text for w in BRAND_WORDS) or is_last or "卖点" in beat or "收口" in beat:
        hits.append(("pop", "品牌 beat", "brand"))
    if any(w in text for w in PAYOFF_WORDS) or "兑现" in beat or "转折" in beat:
        hits.append(("pop", "punchline/兑现", "punchline"))
    if any(w in text for w in REVERSAL_WORDS) or "悬念" in beat:
        hits.append(("whoosh", "反转/转折", "reversal"))
    if any(w in text for w in ACTION_WORDS):
        hits.append(("whoosh", "动作", "action"))
    if any(w in text for w in QUESTION_MARKS):
        hits.append(("ding", "疑问/惊讶", "question"))
    return hits


def plan_sfx(spans, lines, *, genre: str = "", story: dict | None = None,
             sfx_dir: str | Path | None = None, max_hits: int | None = None) -> list[SfxHit]:
    """按台词句时间轴 + 片型 policy 动态放置音效 → [SfxHit]。

    `spans` 是与 `lines` 对齐的 (start, end)（来自 canonical transcript）；
    `story.beat_map` 提供每句的叙事 beat（可选）。
    """
    policy = policy_for(genre)
    limit = policy["max"] if max_hits is None else min(policy["max"], int(max_hits))
    if limit <= 0 or not policy["allow"]:
        return []

    beats = _beat_by_index(story)
    candidates: list[SfxHit] = []
    for i, text in enumerate(lines):
        span = spans[i] if i < len(spans) else (0.0, 0.0)
        start = float(span[0]) if span else 0.0
        beat = beats.get(i + 1, "")
        best: tuple[str, str, str] | None = None
        for kind, reason, trigger in _triggers(str(text), is_last=(i == len(lines) - 1), beat=beat):
            if kind in policy["allow"]:
                best = (kind, reason, trigger)
                break
        if best is None:
            continue
        kind, reason, trigger = best
        candidates.append(SfxHit(at=max(0.0, start - 0.05), file=SFX_FILES[kind], kind=kind,
                                 reason=reason, trigger=trigger, beat=beat,
                                 gain_db=_GAIN_DB.get(kind, 20)))

    # 同一时刻只留一个；按优先序（品牌/兑现 > 反转 > 动作 > 疑问）再按时间裁剪
    candidates.sort(key=lambda h: (_PRIORITY.get(h.trigger, 0), -h.at), reverse=True)
    chosen: list[SfxHit] = []
    seen_times: list[float] = []
    for h in candidates:
        if len(chosen) >= limit:
            break
        if any(abs(h.at - t) < 0.15 for t in seen_times):
            continue
        chosen.append(h)
        seen_times.append(h.at)
    return sorted(chosen, key=lambda h: h.at)


def _beat_by_index(story: dict | None) -> dict[int, str]:
    if not isinstance(story, dict):
        return {}
    out: dict[int, str] = {}
    for item in (story.get("beat_map") or []):
        if isinstance(item, dict):
            try:
                out[int(item.get("index"))] = str(item.get("beat") or "")
            except (TypeError, ValueError):
                continue
    return out


def resolve_files(hits, sfx_dir: str | Path, *,
                  bed_peak: float = SFX_BED_PEAK) -> list[tuple[float, Path, SfxHit]]:
    """把 hits 解析成真实存在的素材路径，并按**实测峰值**定标电平。

    缺素材的行直接丢掉（不静默假混）；量不到峰值的行退回 `SfxHit.gain_db` 兜底。
    """
    base = Path(sfx_dir)
    out: list[tuple[float, Path, SfxHit]] = []
    for hit in hits:
        p = base / hit.file
        if not p.is_file():
            continue
        gain = asset_gain_db(p, target_peak=bed_peak)
        if gain is not None and gain != hit.gain_db:
            out.append((hit.at, p, replace(hit, gain_db=gain)))
        else:
            out.append((hit.at, p, hit))
    return out
