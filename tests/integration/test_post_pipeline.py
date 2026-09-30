"""Phase 9 集成 —— 后期链统一：一条视频一个 canonical transcript；重跑后期不重生视频。

覆盖计划 §Phase 9 验收：
  · 一条视频只产生一个 canonical transcript（重跑后期不产生第二份）；
  · 同一 StorySpec 重跑后期不触发视频重新生成；
  · 字幕/BGM/SFX 全部消费同一份 StorySpec（mood_curve/beat_map）+ 同一份 transcript。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator.models import StageContext
from lib.post import story_audio_brief
from lib.post import transcript as T
from lib.post.audio_director import load_library, select_bgm
from lib.post.sfx import plan_sfx
from tests.unit.test_audio_director import _lib

pytestmark = pytest.mark.integration

UID = "P9POST"
LINES = ["老王说走就走真快", "结果我没想到这么快", "爱优护真省心", "这回是真兑现了"]


@pytest.fixture(autouse=True)
def _no_real_autodl(monkeypatch):
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


class CountingAsr:
    """假 ASR：按台词逐字给时间戳，并计数（用来证明"只推一次"）。"""

    def __init__(self, lines=LINES):
        self.lines = list(lines)
        self.calls = 0

    def __call__(self, video):
        self.calls += 1
        segs, t = [], 0.5
        for line in self.lines:
            words = []
            for ch in line:
                words.append(T.Word(ch, round(t, 3), round(t + 0.2, 3)))
                t = round(t + 0.2, 3)
            segs.append(T.Segment(words[0].start, words[-1].end, line, words))
            t = round(t + 0.1, 3)
        return segs, {"model": "fake-medium", "language": "zh"}


def _story_lines():
    return [{"shot": i // 2 + 1, "speaker": "S2" if i % 2 == 0 else "S1", "text": ln}
            for i, ln in enumerate(LINES)]


def _write_spec(state: Path, genre: str = "G3") -> Path:
    from lib.creative.dna import CreativeDNA
    from lib.creative.storiespec import build_beat_map

    beat_map, mood_curve = build_beat_map({"id": "S", "name": "骨架", "shots": 4},
                                          CreativeDNA(genre=genre))
    doc = {
        "job_uid": UID, "title": "Phase9 后期", "duration": 15, "prompt": "one-take 演示",
        "creative": {"dna": {"genre": genre, "cast_pattern": "@elder_male", "dialogue_mode": "双人对白"}},
        "story_spec": {"uid": UID, "genre": genre, "lines": _story_lines(),
                       "shots": beat_map, "beat_map": beat_map, "mood_curve": mood_curve},
    }
    path = state / f"{UID}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _generate():
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        out = ctx.workspace / "onetake.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 150_000)
        return StageResult.ok("generate", artifacts=[{"type": "video", "path": out}],
                              metrics={"cost": 0.0})

    fn.calls = calls
    return fn


def _package():
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        return StageResult.ok("package", artifacts=[{"type": "package", "path": ctx.workspace}],
                              metrics={})

    fn.calls = calls
    return fn


def _post_compose(asr, library):
    """真跑后期逻辑（canonical → 字幕 → SFX/BGM），只把 ffmpeg 渲染换成落文件。"""
    calls = {"n": 0, "brief": None}

    def fn(ctx):
        calls["n"] += 1
        ws = ctx.workspace
        ws.mkdir(parents=True, exist_ok=True)
        trim = ws / "onetake_trim.mp4"
        if not trim.exists():
            trim.write_bytes(b"t" * 8192)

        doc = json.loads(Path(ctx.spec).read_text(encoding="utf-8"))
        brief = story_audio_brief(doc)
        tr, reused = T.ensure(trim, workspace=ws, transcriber=asr)
        rows = T.build_rows(tr, brief["lines"], max_chars=10)
        spans = T.align_spans(tr, brief["lines"])
        hits = plan_sfx(spans, brief["lines"], genre=brief["genre"], story=brief)
        track, rationale = select_bgm(brief["mood_curve"], brief["beat_map"],
                                      genre=brief["genre"], library=library)
        calls["brief"] = {"rows": len(rows), "sfx": len(hits), "bgm": track.name if track else None,
                          "genre": brief["genre"], "reused": reused, "score": rationale.get("score")}
        final = ws / "onetake_final.mp4"
        final.write_bytes(b"y" * 150_000)
        return StageResult.ok("compose", artifacts=[{"type": "final", "path": final}], metrics={})

    fn.calls = calls
    return fn


def test_post_chain_produces_one_canonical_and_no_regeneration(tmp_state):
    asr = CountingAsr()
    gen = _generate()
    compose = _post_compose(asr, _lib())
    spec = _write_spec(tmp_state, "G3")

    pkg = _package()
    orch = PipelineOrchestrator(store=store,
                                stages={"generate": gen, "compose": compose, "package": pkg},
                                queue_dir=tmp_state / "queue_15s", root=tmp_state,
                                sleep=lambda _s: None)
    result = orch.start(RunConfig(goal="Phase9 后期", source="test",
                                  stages=["generate", "compose", "package"]),
                        specs=[spec], background=False)
    assert result["jobs"] == [UID]
    assert gen.calls["n"] == 1
    assert asr.calls == 1, "一条视频只做一次 ASR"
    assert store.get_job(UID)["status"] == JobState.READY

    ws = tmp_state / "out" / f"gen_{UID}"
    assert sorted(p.name for p in (ws / "transcripts").iterdir()) == ["canonical.json"]
    assert (ws / "onetake_final.mp4").is_file()

    # 同一 StorySpec 再跑一次「后期」：不重生视频、不重推 ASR、不产生第二份 canonical
    compose_again = _post_compose(asr, _lib())
    ctx = StageContext(uid=UID, stage="compose", spec=spec, config=RunConfig(source="test"),
                       workspace=ws, root=tmp_state, state_dir=tmp_state, store=store)
    compose_again(ctx)
    compose_again(ctx)

    assert gen.calls["n"] == 1, "重跑后期不得触发视频重新生成"
    assert asr.calls == 1, "重跑后期不得重新推理 ASR"
    assert sorted(p.name for p in (ws / "transcripts").iterdir()) == ["canonical.json"]
    assert compose_again.calls["brief"]["reused"] is True

    # 队列层面：已完成的任务再 start 也不会重复生产
    again = orch.start(RunConfig(goal="Phase9 后期", source="test",
                                 stages=["generate", "compose", "package"]),
                       specs=[spec], background=False)
    assert again["jobs"] == []
    assert UID in (again.get("skipped") or [])
    assert gen.calls["n"] == 1


def test_post_uses_story_spec_and_transcript_for_subtitles_and_sfx(tmp_state):
    asr = CountingAsr()
    compose = _post_compose(asr, _lib())
    spec = _write_spec(tmp_state, "G3")
    ws = tmp_state / "out" / f"gen_{UID}"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "onetake_trim.mp4").write_bytes(b"t" * 8192)

    ctx = StageContext(uid=UID, stage="compose", spec=spec, config=RunConfig(source="test"),
                       workspace=ws, root=tmp_state, state_dir=tmp_state, store=store)
    compose(ctx)
    brief = compose.calls["brief"]
    assert brief["genre"] == "G3"
    assert brief["rows"] >= 4 and brief["sfx"] >= 1 and brief["bgm"]

    # 字幕时间必须与 transcript 对齐结果一致（同一份事实源）
    tr = T.load(ws)
    doc = json.loads(spec.read_text(encoding="utf-8"))
    lines = story_audio_brief(doc)["lines"]
    assert T.align_spans(tr, lines)[0][0] == T.build_rows(tr, lines, max_chars=10)[0][0]

    # 换片型（情感片 G5）→ SFX 策略立刻不同（不塞 ding/whoosh/pop）
    doc["creative"]["dna"]["genre"] = "G5"
    spec.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    compose_g5 = _post_compose(CountingAsr(), _lib())
    compose_g5(ctx)
    assert compose_g5.calls["brief"]["sfx"] == 0


def test_real_bgm_library_metadata_is_curated_for_most_tracks():
    lib = load_library(Path("assets/bgm_trending"))
    assert len(lib) >= 30
    curated = [t for t in lib if t.source == "sidecar"]
    assert len(curated) >= 20, "真实曲库应有 metadata sidecar 覆盖"
    for t in curated:
        assert t.mood in {"upbeat", "comedic", "emotional", "calm", "epic", "neutral"}
        assert 0.0 <= t.energy <= 1.0
