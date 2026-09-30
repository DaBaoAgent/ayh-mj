"""Phase 15 验收共享装置（只验收不加功能：装置全部是测试侧替身）。

计划 §15.1 要求"使用 fake provider + fixture media"完成多条无付费全链，因此这里把
三类**外部输入**替换成可复现 fixture，而产线的判定逻辑一律用真实实现：

  1. 台词稿（写作步骤）：产线口径是 `docs/onetake_lines_<uid>.txt`（人工/写作步骤产出），
     验收里由 `install_lines()` 提供 —— 与"fixture media 替真实成片"同口径，
     不是"人工预放 queue spec"（选题/骨架/角色/钩子仍由 Planner 自主决定）；
  2. 画面/转写观感（vision/transcript/subtitle）：`evidence()` 按 spec 现造证据，
     真正判定仍走 `lib.qa.critic` + `lib.orchestrator.stages._qa_gate`；
  3. 后期渲染：`compose` fixture 落 `onetake_final.mp4`，但最终验片仍走产线 QA 门。

发布用 fake 适配器（`FakePublishAdapter`），确保验收不会真发社媒。
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.orchestrator import PipelineOrchestrator, StageResult
from lib.orchestrator import stages as stages_mod
from tests.fakes.providers import FakeProvider

# 真实 delivery 检查要求成片 >= 100000 字节，fixture 成片必须真的大于这个数
VIDEO_BYTES = b"fixture-mp4-payload" * 6000

# 台词 fixture：按台词模式给稿（写作步骤的替身）
MODE_LINES: dict[str, list[str]] = {
    "双人对白": ["这个真的能行吗", "你自己看，单手就拎起来了", "真有这么轻", "对，单手就够"],
    "单人口播": ["今天当着大家的面做个小测试", "先看这个折叠动作", "再看它在窄道里的表现"],
    "街访问答": ["您猜这个有多重", "看着挺沉，其实单手就能提", "真没想到这么轻"],
    "画外音旁白": ["早上出门，它就在门口等着", "路上遇到台阶，推着就过去了",
                   "晚上回家，收起来不占地方"],
    "字幕驱动": ["画面出现一个神秘包装", "拆开后露出整车"],
    "无对白": [],
}


def install_lines(monkeypatch):
    """把产线"写作步骤"（docs/onetake_lines_<uid>.txt）替换成 fixture 台词稿。

    Planner 与 Compiler 各自 import 了 `lines_from_file`，两处都要替换，
    否则"落进 spec 的台词"与"编译期回退读到的台词"会走不同来源。
    """
    def fake(uid, n_shots, dialogue_mode, slots):
        mode = str(dialogue_mode or "")
        # 未登记的说词模式给一条通用稿：缺稿是 Phase 7 门禁的课题，
        # 不该在"全链能跑通"的验收里把任务卡住（无对白模式仍返回空）。
        texts = MODE_LINES.get(mode, ["这个设计真的不一样", "你看这里，细节都在手上"])
        if not texts:
            return []
        two = str(dialogue_mode) == "双人对白" and len(slots) >= 2
        out: list[dict] = []
        n = max(1, len(texts))
        n_shots = max(1, int(n_shots or 1))
        for i, text in enumerate(texts):
            shot = min(n_shots, 1 + int(i * n_shots / n))
            if not slots:
                speaker = "S1"
            elif two:
                speaker = slots[0] if i % 2 == 0 else slots[1 % len(slots)]
            else:
                speaker = slots[0]
            out.append({"shot": shot, "speaker": speaker, "text": text})
        return out

    import lib.creative.compiler as compiler_mod
    import lib.creative.planner as planner_mod
    monkeypatch.setattr(planner_mod, "lines_from_file", fake)
    monkeypatch.setattr(compiler_mod, "lines_from_file", fake)
    return fake


def no_real_autodl(monkeypatch):
    """Phase 13/15 硬约束：自动测试里任何真实的 AutoDL 提交都必须炸出来。"""
    import s4_generate.autodl_client as ac

    def boom(*_a, **_k):
        raise AssertionError("自动测试不得真的提交 AutoDL 任务")

    monkeypatch.setattr(ac, "create_task", boom, raising=False)
    return boom


# ── spec / DNA 读取 ───────────────────────────────────────────────────
def _read_json(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def spec_of(store_, uid: str, queue_dir=None) -> dict:
    """读一条 spec 的完整 JSON。

    出片成功后 spec 会被归档进 `queue_15s/_done/`（Phase 3 口径：artifact 只是历史指针），
    因此这里先认 artifact 路径，再回退到归档目录。
    """
    for art in store_.list_artifacts(uid, "spec"):
        path = art.get("path")
        if path and Path(path).is_file():
            return _read_json(path)
    if queue_dir is not None:
        for cand in (Path(queue_dir) / f"{uid}.json",
                     Path(queue_dir) / "_done" / f"{uid}.json"):
            if cand.is_file():
                return _read_json(cand)
    return {}


def dna_of(store_, uid: str) -> dict:
    """读一条 job 的 CreativeDNA（creative_dna artifact 不会随出片归档）。"""
    for art in store_.list_artifacts(uid, "creative_dna"):
        path = art.get("path")
        if path and Path(path).is_file():
            payload = _read_json(path)
            dna = payload.get("dna") or {}
            if dna:
                return dna
    return {}


def planned_docs(planned) -> dict:
    """把 `plan_missing` / `plan_batch` 的返回变成 {uid: spec JSON}。

    这是**不依赖 artifact/归档**的读法：规划刚结束时 spec 就在 `spec_path` 上，
    因此多样性统计与成本断言都该走这里，而不是走"会被归档"的 artifact。
    """
    out: dict[str, dict] = {}
    for pj in planned or []:
        path = getattr(pj, "spec_path", None)
        if path and Path(path).is_file():
            out[pj.uid] = _read_json(path)
    return out


def doc_lines(doc: dict) -> list[dict]:
    rows = (doc.get("story_spec") or {}).get("lines") or []
    return [r for r in rows if isinstance(r, dict) and str(r.get("text") or "").strip()]


def doc_dna(doc: dict) -> dict:
    return ((doc.get("creative") or {}).get("dna")
            or (doc.get("story_spec") or {}).get("dna") or {})


def doc_duration(doc: dict) -> float:
    story = doc.get("story_spec") or {}
    return float(doc.get("duration") or story.get("duration") or 15.0)


def doc_people(doc: dict) -> int:
    pattern = str(doc_dna(doc).get("cast_pattern") or "")
    return len([s for s in pattern.split("+") if s.strip()]) or 1


def spec_reader(store_, queue_dir=None, cache: dict | None = None):
    """按需读 spec 的回调（自主规划在本阶段内才生成 uid，不能预读）。

    **不缓存空结果**：出片成功后 spec 会被归档进 `queue_15s/_done/`；
    归档前读到 `{}` 的 uid 之后必须还能重新读到（缓存空值会把回退读法打掉）。
    """
    seen: dict[str, dict] = dict(cache or {})

    def read(uid: str) -> dict:
        doc = seen.get(uid)
        if not doc:
            doc = spec_of(store_, uid, queue_dir)
            if doc:
                seen[uid] = doc
        return doc

    read.cache = seen
    return read


# ── QA 证据（按 spec 现造；真实判定交给 lib.qa.critic）────────────────
def evidence(doc: dict, *, products_seen: int | None = None, product_deformed: bool = False,
             deformed_parts=(), wrong_speaker_shots=(), non_speaker_mouth_open: bool = False,
             anatomy_ok: bool = True, transcript_text: str | None = None,
             subtitle: dict | None = None, subtitle_cues: list | None = None,
             people_seen: int | None = None, static_seconds: float = 0.5,
             first_hook_seconds: float = 1.0, payoff_ratio: float = 0.8,
             tail_silence_seconds: float = 0.2) -> dict:
    """按 spec 造一份 QA 证据；四类验收 fixture 通过关键字参数注入缺陷。

    默认证据是"干净的"：产品数 / 人数 / 台词 / 字幕全部与 spec 对齐。
    """
    lines = doc_lines(doc)
    texts = [str(x.get("text")) for x in lines]
    spoken = " ".join(texts)
    duration = doc_duration(doc)
    people = doc_people(doc)
    n = max(1, len(texts))
    if subtitle_cues is None:
        cues = [{"start": round(duration * i / n, 2), "end": round(duration * (i + 1) / n, 2),
                 "text": text} for i, text in enumerate(texts)]
    else:
        cues = subtitle_cues
    sub = subtitle if subtitle is not None else {"cues": cues, "wrap_ok": True, "safe_area_ok": True}
    return {
        "video": {"exists": True, "bytes": len(VIDEO_BYTES), "video_streams": 1,
                  "audio_streams": 1, "duration": duration,
                  "loudness_lufs": -14.0, "true_peak_db": -1.5},
        "vision": {"products_seen": 1 if products_seen is None else products_seen,
                   "product_deformed": bool(product_deformed),
                   "deformed_parts": list(deformed_parts),
                   "anatomy_ok": bool(anatomy_ok),
                   "wrong_speaker_shots": list(wrong_speaker_shots),
                   "non_speaker_mouth_open": bool(non_speaker_mouth_open),
                   "people_seen": people if people_seen is None else people_seen,
                   "first_hook_seconds": first_hook_seconds,
                   "static_seconds": static_seconds,
                   "payoff_seconds": round(duration * payoff_ratio, 2)},
        "spec": {"duration": duration, "products_expected": 1, "people_expected": people,
                 "dialogue_mode": str(doc_dna(doc).get("dialogue_mode") or ""),
                 "expected_lines": [{"shot": x.get("shot"), "speaker": x.get("speaker"),
                                     "text": x.get("text")} for x in lines]},
        "transcript": {"text": spoken if transcript_text is None else transcript_text,
                       "tail_silence_seconds": tail_silence_seconds},
        "subtitle": sub,
        "copy": {"title": str(doc.get("title") or ""), "spoken": spoken,
                 "on_screen": "", "description": ""},
    }


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def write_evidence(ctx, payload: dict, *, phase: str = "gen") -> Path:
    name = f"qa_evidence_{ctx.uid}.json" if phase == "gen" else f"qa_final_evidence_{ctx.uid}.json"
    return write_json(ctx.workspace / name, payload)


# ── 阶段包装/替身 ─────────────────────────────────────────────────────
def stage_generate(*, pad_to: int = len(VIDEO_BYTES)):
    """真实 generate 阶段（经 FakeProvider 提交/下载）+ 把 fixture 补到成片尺寸。"""
    calls = {"n": 0}

    def fn(ctx):
        calls["n"] += 1
        res = stages_mod.stage_generate(ctx)
        out = ctx.workspace / "onetake.mp4"
        if res.success and not ctx.dry and out.is_file() and out.stat().st_size < pad_to:
            out.write_bytes(VIDEO_BYTES)
        return res

    fn.calls = calls
    return fn


def stage_qa(doc_for, *, evidence_for=None, phase: str = "gen"):
    """真实 qa 阶段 + fixture 证据。`evidence_for(uid, attempt_no)` 可注入缺陷。"""
    calls: dict[str, int] = {}

    def fn(ctx):
        n = calls[ctx.uid] = calls.get(ctx.uid, 0) + 1
        payload = evidence_for(ctx.uid, n) if evidence_for else None
        if payload is None:
            payload = evidence(doc_for(ctx.uid))
        write_evidence(ctx, payload, phase=phase)
        return stages_mod.stage_qa(ctx)

    fn.calls = calls
    return fn


def stage_compose(doc_for, *, evidence_for=None):
    """fixture 后期：落 onetake_final.mp4 + final 证据，验片仍走产线真实门禁。"""
    calls: dict[str, int] = {}

    def fn(ctx):
        n = calls[ctx.uid] = calls.get(ctx.uid, 0) + 1
        src = ctx.workspace / "onetake.mp4"
        final = ctx.workspace / "onetake_final.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(src.read_bytes() if src.is_file() else VIDEO_BYTES)
        payload = evidence_for(ctx.uid, n) if evidence_for else None
        if payload is None:
            payload = evidence(doc_for(ctx.uid))
        write_evidence(ctx, payload, phase="final")
        gate = stages_mod._qa_gate(ctx, phase="final", stage="compose")
        artifacts = [{"type": "final", "path": final}, *gate.artifacts]
        if not gate.success:
            return StageResult.fail("compose", gate.error_code or "QA_FAILED", gate.message,
                                    metrics=dict(gate.metrics), artifacts=artifacts,
                                    data=dict(gate.data))
        return StageResult.ok("compose", artifacts=artifacts,
                              metrics={"bytes": final.stat().st_size, **gate.metrics},
                              message="fixture 后期合成完成")

    fn.calls = calls
    return fn


def new_provider() -> FakeProvider:
    provider = FakeProvider()
    provider.payload_bytes = VIDEO_BYTES
    return provider


def build_orchestrator(store_, tmp_state, *, docs=None, planned=None, provider=None,
                       queue_dir=None, qa_evidence_for=None, compose_evidence_for=None,
                       stages_override: dict | None = None, **kwargs):
    """标准验收编排器：plan/preflight/generate/qa/package 真实，只有后期渲染是 fixture。

    `docs` 可以是 dict（uid -> spec）或可调用对象；`planned` 是 `plan_missing` 的返回
    （预注入 spec 内容，避开归档）；两者都缺省时按需从 JobStore 读。
    """
    provider = provider if provider is not None else new_provider()
    queue_dir = Path(queue_dir) if queue_dir is not None else tmp_state / "queue_15s"
    cache: dict = {}
    if planned:
        cache.update(planned_docs(planned))
    if isinstance(docs, dict):
        cache.update(docs)
    doc_for = (docs if (docs is not None and not isinstance(docs, dict))
               else spec_reader(store_, queue_dir, cache=cache))
    stages = {
        "plan": stages_mod.stage_plan,
        "preflight": stages_mod.stage_preflight,
        "generate": stage_generate(),
        "qa": stage_qa(doc_for, evidence_for=qa_evidence_for),
        "compose": stage_compose(doc_for, evidence_for=compose_evidence_for),
        "package": stages_mod.stage_package,
    }
    if stages_override:
        stages.update(stages_override)      # 仅验收装置用：替换单个 stage 以注入故障
    return PipelineOrchestrator(
        store=store_, stages=stages, provider=provider, queue_dir=queue_dir,
        root=tmp_state, sleep=lambda _s: None, **kwargs)


# ── 发布替身 ──────────────────────────────────────────────────────────
class FakePublishAdapter:
    """发布通道替身：可编排每个平台的返回，绝不真发。"""

    def __init__(self, *, status: str = "SUCCESS", platform_status: dict | None = None,
                 error: str = "", post_id: str = "fake_post") -> None:
        self.status = status
        self.platform_status = dict(platform_status or {})
        self.error = error
        self.post_id = post_id
        self.calls: list[dict] = []

    def publish(self, *, uid, job, brief, platform, copy, mode) -> dict:
        self.calls.append({"uid": uid, "platform": platform, "mode": mode, "copy": dict(copy)})
        status = self.platform_status.get(platform, self.status)
        out: dict = {"status": status}
        if status in ("SUCCESS", "DRAFT"):
            out["post_id"] = f"{self.post_id}_{platform}"
            out["post_url"] = f"https://example.invalid/{uid}/{platform}"
        if status == "AUTH_EXPIRED":
            out["error"] = self.error or "凭据失效（fake）"
        if status == "FAILED":
            out["error"] = self.error or "fake publish failed"
        return out

    @property
    def platforms(self) -> list[str]:
        return [c["platform"] for c in self.calls]


# ── 多样性统计（计划 §15.4 口径）───────────────────────────────────────
DIVERSITY_DIMS = ("genre", "hook_type", "shot_pattern", "dialogue_mode", "cast_pattern", "angle")


def diversity(docs: list[dict]) -> dict:
    """按 CreativeDNA 维度统计多样性；入参是**完整 spec JSON**（risk_of 需要 structure_id/CTA）。"""
    from lib.creative.prescreen import needs_prescreen

    dnas = [doc_dna(d) for d in docs]
    out: dict = {}
    for key in DIVERSITY_DIMS:
        vals = {str((d or {}).get(key) or "") for d in dnas} - {""}
        out[key] = {"count": len(vals), "values": sorted(vals)}
    out["cast_size"] = sorted(doc_people(d) for d in docs)
    out["combos"] = ["|".join(str(doc_dna(d).get(k) or "")
                              for k in ("genre", "hook_type", "angle", "cast_pattern"))
                     for d in docs]
    out["prescreen"] = sum(1 for d in docs if needs_prescreen(d))
    return out
