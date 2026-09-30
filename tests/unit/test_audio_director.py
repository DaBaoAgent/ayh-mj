"""Phase 9 单元 —— AudioDirector：BGM metadata + 依 StorySpec 选曲。

对应计划 §Phase 9 必做 6/7/8 与验收「≥5 种 genre 的 BGM/SFX 选择策略明显不同」。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.post import audio_director as AD

pytestmark = pytest.mark.unit

GENRES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")


def _lib() -> list[AD.BgmTrack]:
    """合成曲库：覆盖 6 种 mood 的确定性 metadata（不需要真音频文件）。"""
    def t(name, mood, energy, comedic, emotional, genre):
        return AD.BgmTrack(path=f"/x/{name}", name=name, mood=mood, energy=energy,
                           comedic=comedic, emotional=emotional, genre=genre)

    return [
        t("comedic_high.mp3", "comedic", 0.90, 0.95, 0.05, "comedy"),
        t("upbeat_pop.mp3", "upbeat", 0.80, 0.40, 0.25, "pop"),
        t("emotional_warm.mp3", "emotional", 0.25, 0.05, 0.90, "emotional"),
        t("calm_soft.mp3", "calm", 0.20, 0.05, 0.50, "calm"),
        t("epic_rise.mp3", "epic", 0.80, 0.10, 0.30, "epic"),
        t("neutral_bed.mp3", "neutral", 0.50, 0.30, 0.30, "neutral"),
    ]


CURVE = [{"index": 1, "beat": "钩子", "mood": "upbeat", "energy": 0.85},
         {"index": 2, "beat": "冲突/悬念", "mood": "epic", "energy": 0.8}]


# ── 任务 6：metadata 的 9 个字段必须齐全 ─────────────────────────
def test_bgm_metadata_has_all_required_fields():
    track = AD.BgmTrack(path="/x/a.mp3", name="a.mp3")
    for field in ("bpm", "energy", "mood", "intro_strength", "drop_time",
                  "genre", "vocal", "comedic", "emotional"):
        assert field in track.to_dict(), field
    assert track.has_all_fields()


def test_infer_metadata_is_deterministic_and_size_independent(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "搞笑滑稽.mp3").write_bytes(b"x" * 1000)       # 小
    (tmp_path / "b" / "搞笑滑稽.mp3").write_bytes(b"x" * 5_000_000)   # 大
    la = AD.load_library(tmp_path / "a")
    lb = AD.load_library(tmp_path / "b")
    assert la[0].to_dict() | {"path": ""} == lb[0].to_dict() | {"path": ""}
    assert la[0].mood == "comedic" and la[0].comedic > 0.8


def test_load_library_sidecar_overrides_inference(tmp_path):
    (tmp_path / "x.mp3").write_bytes(b"x")
    (tmp_path / "_metadata.json").write_text(json.dumps(
        {"x.mp3": {"mood": "epic", "bpm": 128, "emotional": 0.77}}), encoding="utf-8")
    track = AD.load_library(tmp_path)[0]
    assert track.source == "sidecar"
    assert track.mood == "epic" and track.bpm == 128 and track.emotional == 0.77


# ── 任务 7/8：确定性、由故事驱动、最近未使用非唯一逻辑 ────────────
def test_select_bgm_is_deterministic():
    lib = _lib()
    a, ra = AD.select_bgm(CURVE, [], genre="G3", library=lib)
    b, rb = AD.select_bgm(CURVE, [], genre="G3", library=lib)
    assert a.name == b.name
    assert ra["score"] == rb["score"]
    assert ra["candidates"] and ra["score_parts"]


def test_mood_curve_drives_selection_not_file_size():
    """同样曲库、不同 mood_curve → 不同选曲（证明是故事驱动的）。"""
    lib = _lib()
    comedic = [{"mood": "comedic", "energy": 0.9}]
    warm = [{"mood": "emotional", "energy": 0.25}]
    t1, _ = AD.select_bgm(comedic, [], genre="G1", library=lib)
    t2, _ = AD.select_bgm(warm, [], genre="G1", library=lib)
    assert t1.name != t2.name
    assert t1.mood == "comedic" and t2.mood == "emotional"


def test_recent_unused_is_a_penalty_but_not_the_only_logic():
    lib = _lib()
    base, _ = AD.select_bgm(CURVE, [], genre="G3", library=lib)
    penalised, rationale = AD.select_bgm(CURVE, [], genre="G3", library=lib,
                                         recent={base.name})
    assert penalised.name != base.name, "最近用过要降权"
    cands = {c["name"]: c for c in rationale["candidates"]}
    assert cands[base.name]["recent_penalty"] < 0

    # 但当一个 track 与故事唯一匹配时，即便"最近用过"也必须选它（不是唯一逻辑）
    only = [t for t in lib if t.mood == "comedic"]
    forced, _ = AD.select_bgm([{"mood": "comedic", "energy": 0.9}], [], genre="G3",
                              library=only, recent={only[0].name})
    assert forced.name == only[0].name


def _curve_for(genre: str) -> list[dict]:
    """走真实链路：片型 → StorySpec.beat_map/mood_curve → AudioDirector。"""
    from lib.creative.dna import CreativeDNA
    from lib.creative.storiespec import build_beat_map

    _, curve = build_beat_map({"id": "S", "name": "骨架", "shots": 4}, CreativeDNA(genre=genre))
    return curve


def test_at_least_five_genres_pick_different_strategies():
    """验收：≥5 个片型的选曲策略（mood_curve→选曲）明显不同。"""
    lib = _lib()
    picks, profiles, curves = {}, {}, {}
    for g in GENRES:
        curve = _curve_for(g)
        track, rationale = AD.select_bgm(curve, [], genre=g, library=lib)
        picks[g] = track.name
        profiles[g] = (rationale["mood_target"], tuple(rationale["profile"]["mood"]))
        curves[g] = tuple((c["mood"], c["energy"]) for c in curve)
    assert len(set(picks.values())) >= 5, picks
    assert len(set(profiles.values())) >= 5, profiles
    assert len(set(curves.values())) >= 5, curves


def test_empty_library_returns_none_without_crashing():
    track, rationale = AD.select_bgm(CURVE, [], genre="G3", library=[])
    assert track is None
    assert rationale["error"]


def test_pick_bgm_facade_returns_a_path_from_a_real_dir(tmp_path):
    (tmp_path / "搞笑滑稽.mp3").write_bytes(b"x")
    picked = AD.pick_bgm("G3", mood_curve=[{"mood": "comedic", "energy": 0.9}], lib_dir=tmp_path)
    assert picked is not None and Path(picked).name == "搞笑滑稽.mp3"
