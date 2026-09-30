"""AudioDirector —— BGM 元数据 + 按剧情节拍选曲（Phase 9 必做 6/7/8）。

Phase 9 之前的两套选曲都违规：
  · `tools/make_15s.py`：`sorted(pool, size)[0]` —— 按**文件大小**选，等于不看内容；
  · `tools/audio_polish.py`：`random.choice` —— 每次不同，不可复现、不可解释。

现在只有一套：给每首 BGM 建 metadata（BPM/energy/mood/intro_strength/drop_time/
genre/vocal/comedic/emotional），再由 StorySpec 的 `mood_curve` / `beat_map` 与片型
profile 打分选曲。「最近未使用」保留为**防重复惩罚项**，但绝不是唯一逻辑。

全部确定性：同输入恒得同一首（无 random、无 filesize），并给出可解释的 rationale。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

BGM_META_FIELDS = ("bpm", "energy", "mood", "intro_strength", "drop_time",
                   "genre", "vocal", "comedic", "emotional")
MOODS = ("upbeat", "comedic", "emotional", "calm", "epic", "neutral")

# 片型 → BGM profile（这是"不同 genre 明显不同"的来源；改这里就改片型气质）
GENRE_BGM_PROFILE: dict[str, dict] = {
    "G1": {"mood": ["neutral", "upbeat", "epic"], "energy": 0.55, "comedic": 0.30, "emotional": 0.40},
    "G2": {"mood": ["upbeat", "epic"], "energy": 0.85, "comedic": 0.50, "emotional": 0.35},
    "G3": {"mood": ["comedic", "upbeat"], "energy": 0.85, "comedic": 0.90, "emotional": 0.10},
    "G4": {"mood": ["comedic", "upbeat"], "energy": 0.70, "comedic": 0.80, "emotional": 0.20},
    "G5": {"mood": ["emotional", "calm"], "energy": 0.25, "comedic": 0.05, "emotional": 0.90},
    "G6": {"mood": ["neutral", "calm"], "energy": 0.35, "comedic": 0.25, "emotional": 0.35},
    "G7": {"mood": ["calm", "neutral"], "energy": 0.30, "comedic": 0.15, "emotional": 0.40},
    "G8": {"mood": ["comedic"], "energy": 0.90, "comedic": 0.95, "emotional": 0.05},
    "G9": {"mood": ["epic", "calm"], "energy": 0.50, "comedic": 0.10, "emotional": 0.55},
    "G10": {"mood": ["upbeat", "epic"], "energy": 0.75, "comedic": 0.20, "emotional": 0.20},
}
DEFAULT_PROFILE = {"mood": ["neutral"], "energy": 0.5, "comedic": 0.3, "emotional": 0.3}

# 关键词 → (mood, energy, comedic, emotional)；命中多个取第一个
_KEYWORDS: list[tuple[tuple[str, ...], str, float, float, float]] = [
    (("搞笑", "滑稽", "沙雕", "爆笑", "搞怪", "欢乐", "逗", "调皮", "猪八戒", "魔性"), "comedic", 0.85, 0.9, 0.05),
    (("温情", "温暖", "归家", "思念", "泪", "回忆", "阳光", "岁月", "母亲", "父亲"), "emotional", 0.30, 0.05, 0.9),
    (("舒缓", "安静", "钢琴", "轻音乐", "疗愈", "静谧", "冥想"), "calm", 0.25, 0.05, 0.5),
    (("燃", "摇滚", "劲爆", "史诗", "磅礴", "震撼", "战斗", "蹦迪", "节奏"), "epic", 0.90, 0.10, 0.3),
    (("轻快", "欢快", "清新", "爵士", "明朗", "雀跃", "喜庆", "新年", "阳光"), "upbeat", 0.70, 0.35, 0.3),
]


def _stable(text: str) -> int:
    """跨进程稳定的整数哈希（Python 内置 hash 每次进程不同，不能用）。"""
    return int(hashlib.md5(str(text).encode("utf-8")).hexdigest()[:8], 16)


def _unit(text: str, salt: str = "") -> float:
    return round((_stable(f"{text}|{salt}") % 1000) / 1000.0, 3)


def infer_metadata(name: str) -> dict:
    """无 sidecar 时，从文件名推一份**确定性** metadata（不靠文件大小、不随机）。"""
    mood, energy, comedic, emotional = "neutral", 0.5, 0.3, 0.3
    for keys, m, e, c, em in _KEYWORDS:
        if any(k in name for k in keys):
            mood, energy, comedic, emotional = m, e, c, em
            break
    vocal = any(k in name for k in ("唱", "歌", "人声", "女声", "男声", "童声"))
    bpm_lo, bpm_hi = (120, 140) if energy >= 0.8 else (100, 120) if energy >= 0.6 else (70, 95)
    return {
        "bpm": bpm_lo + int(_unit(name, "bpm") * (bpm_hi - bpm_lo)),
        "energy": energy,
        "mood": mood,
        "intro_strength": round(0.4 + 0.6 * _unit(name, "intro"), 3),
        "drop_time": round(4.0 + 16.0 * _unit(name, "drop"), 2),
        "genre": {"comedic": "comedy", "emotional": "emotional", "calm": "calm",
                  "epic": "epic", "upbeat": "pop", "neutral": "neutral"}[mood],
        "vocal": vocal,
        "comedic": comedic,
        "emotional": emotional,
    }


@dataclass
class BgmTrack:
    path: str
    name: str
    bpm: int = 100
    energy: float = 0.5
    mood: str = "neutral"
    intro_strength: float = 0.5
    drop_time: float = 8.0
    genre: str = "neutral"
    vocal: bool = False
    comedic: float = 0.3
    emotional: float = 0.3
    source: str = "inferred"

    def to_dict(self) -> dict:
        d = {"path": self.path, "name": self.name, "source": self.source}
        d.update({k: getattr(self, k) for k in BGM_META_FIELDS})
        return d

    def has_all_fields(self) -> bool:
        return all(hasattr(self, k) for k in BGM_META_FIELDS)


def _track_from(path: Path, name: str, meta: dict | None) -> BgmTrack:
    base = infer_metadata(name)
    if meta:
        base.update({k: v for k, v in meta.items() if k in BGM_META_FIELDS})
        source = "sidecar"
    else:
        source = "inferred"
    return BgmTrack(path=str(path), name=name, source=source, **base)


def load_library(lib_dir: str | Path, *, pattern: str = "*.mp3") -> list[BgmTrack]:
    """扫目录建曲库；`_metadata.json`（{name: {字段...}}）可覆盖推断值。"""
    lib = Path(lib_dir)
    if not lib.is_dir():
        return []
    sidecar: dict = {}
    meta_file = lib / "_metadata.json"
    if meta_file.is_file():
        try:
            sidecar = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sidecar = {}
    tracks = []
    for p in sorted(lib.glob(pattern)):
        if p.name.startswith("_"):
            continue
        meta = sidecar.get(p.name) if isinstance(sidecar.get(p.name), dict) else None
        tracks.append(_track_from(p, p.name, meta))
    return tracks


def _norm_curve(mood_curve, beat_map=None) -> tuple[str, float, list[str]]:
    """mood_curve / beat_map → (主要 mood, 目标能量, mood 序列)。两种输入都容错。"""
    moods: list[str] = []
    energies: list[float] = []
    for item in (mood_curve or []):
        if isinstance(item, dict):
            m = str(item.get("mood") or "").strip()
            if m:
                moods.append(m)
            e = item.get("energy")
            if isinstance(e, (int, float)):
                energies.append(float(e))
        elif isinstance(item, str) and item.strip():
            moods.append(item.strip())
    for item in (beat_map or []):
        if isinstance(item, dict):
            m = str(item.get("mood") or "").strip()
            if m:
                moods.append(m)
            e = item.get("energy")
            if isinstance(e, (int, float)):
                energies.append(float(e))
    target_mood = max(sorted(set(moods)), key=moods.count) if moods else "neutral"
    target_energy = round(sum(energies) / len(energies), 3) if energies else 0.5
    return target_mood, target_energy, moods


def score_track(track: BgmTrack, profile: dict, *, mood_target: str, energy_target: float,
                moods: list[str], recent: set[str]) -> tuple[float, dict]:
    parts: dict = {}
    # 与 StorySpec mood_curve 的直接一致度是**最高权重**（任务 7：由故事驱动，不是由大小驱动）；
    # 片型 profile 只是先验/兜底（mood 命中、能量与情绪气质）。
    if moods:
        hit = sum(1 for m in moods if m == track.mood) / len(moods)
        parts["mood_curve"] = round(3.0 * hit, 3)
    else:
        parts["mood_curve"] = 0.0
    parts["mood_prior"] = 1.0 if track.mood in profile["mood"] else (
        0.5 if track.mood == "neutral" else 0.0)
    parts["energy"] = round(2.0 * (1.0 - abs(track.energy - energy_target)), 3)
    parts["profile_energy"] = round(
        0.5 * (1.0 - abs(track.energy - float(profile.get("energy", 0.5)))), 3)
    parts["comedic"] = round(1.0 * (1.0 - abs(track.comedic - float(profile.get("comedic", 0.3)))), 3)
    parts["emotional"] = round(1.0 * (1.0 - abs(track.emotional - float(profile.get("emotional", 0.3)))), 3)
    # 「最近未使用」只作为防重复惩罚项，不是唯一逻辑（任务 8）
    parts["recent_penalty"] = -4.0 if track.name in recent else 0.0
    score = round(sum(parts.values()), 4)
    return score, parts


def select_bgm(mood_curve=None, beat_map=None, *, genre: str = "", library=None,
               recent=(), lib_dir: str | Path | None = None) -> tuple[BgmTrack | None, dict]:
    """按 StorySpec 选 BGM → (track, rationale)。确定性；无曲库返回 (None, {...})。"""
    if library is None:
        if lib_dir is None:
            from ..settings import get_settings

            s = get_settings()
            lib_dir = s.paths.bgm_lib or (s.root / "assets" / "bgm_trending")
        library = load_library(lib_dir)
    tracks = list(library or [])
    if not tracks:
        return None, {"genre": genre, "error": "空曲库", "candidates": []}

    profile = GENRE_BGM_PROFILE.get(genre, DEFAULT_PROFILE)
    mood_target, energy_target, moods = _norm_curve(mood_curve, beat_map)
    recent_set = {str(r) for r in (recent or [])}

    scored = []
    for t in tracks:
        s, parts = score_track(t, profile, mood_target=mood_target, energy_target=energy_target,
                               moods=moods, recent=recent_set)
        scored.append((s, t, parts))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    best_score, best, parts = scored[0]
    rationale = {
        "genre": genre, "profile": profile,
        "mood_target": mood_target, "energy_target": energy_target,
        "mood_curve": list(moods), "recent": sorted(recent_set),
        "chosen": best.name, "score": best_score, "score_parts": parts,
        "recent_used": best.name in recent_set,
        "candidates": [{"name": t.name, "score": s, "mood": t.mood, "energy": t.energy,
                        "recent_penalty": parts_.get("recent_penalty", 0.0)}
                       for s, t, parts_ in scored],
    }
    return best, rationale


def pick_bgm(genre: str = "", *, mood_curve=None, beat_map=None, recent=(), lib_dir=None) -> Path | None:
    """兼容门面：老调用点要一个 Path。内部走 select_bgm（无 random、无 filesize）。"""
    track, _ = select_bgm(mood_curve, beat_map, genre=genre, recent=recent, lib_dir=lib_dir)
    return Path(track.path) if track else None
