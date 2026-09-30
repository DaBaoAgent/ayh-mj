"""QA Critic（Phase 8）—— 收集证据 → 判定 → 给 RepairEngine 一个明确的 error_code。

分工
  · `gather_evidence()`：从真实产物能拿到什么就拿什么（ffprobe 探成片、读字幕/转写
    artifact、读 spec 期望值、跑合规门）。**拿不到的证据一律留空**，由 `checks` 记成
    `skipped`，绝不把"没看"当成"通过"。
  · `QaCritic.analyze()`：纯判定（跑 `checks.run_checks`），产出 `QaReport`。
  · 画面类证据（产品形变/解剖/说话人）由一个 `vision` 段承载：Phase 8 由
    `qa_evidence_<uid>.json` / `qa_final_evidence_<uid>.json` 提供（fixture、人工复核或
    多模态模型回填），Phase 9+ 可直接接 `media_analysis`。

两处调用点（与 `STAGE_ORDER` 对齐）：
  · `stage_qa`        —— phase="gen"，验生成产物 `onetake.mp4`；
  · `stage_compose`   —— phase="final"，验合成产物 `onetake_final.mp4`（字幕/响度在此）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .checks import coverage, run_checks
from .report import DIMENSIONS, QaReport

# 每处调用点该验哪些维度（"这一步修得动什么"）：
#   gen   —— 生成产物：画面/人物/对白/留存/合规 + 成片完整性
#   final —— 合成产物：字幕/响度/成片完整性（画面已在前一步验过）
PHASE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "gen": DIMENSIONS,
    "final": ("delivery", "audio"),
}

PHASES: tuple[str, ...] = ("gen", "final")
EVIDENCE_FILENAME = {"gen": "qa_evidence_{uid}.json", "final": "qa_final_evidence_{uid}.json"}
VIDEO_FILENAME = {"gen": "onetake.mp4", "final": "onetake_final.mp4"}
TRANSCRIPT_FILENAME = {"gen": "transcript_{uid}.json", "final": "transcript_{uid}.json"}


def evidence_path(workspace: Path, uid: str, phase: str = "gen") -> Path:
    pattern = EVIDENCE_FILENAME.get(phase, EVIDENCE_FILENAME["gen"])
    return Path(workspace) / pattern.format(uid=uid)


def video_path(workspace: Path, uid: str, phase: str = "gen") -> Path:
    return Path(workspace) / VIDEO_FILENAME.get(phase, VIDEO_FILENAME["gen"])


def load_evidence(workspace: Path, uid: str, phase: str = "gen") -> dict:
    """读证据文件；不存在/损坏都返回 {}（调用方会把它记成 skipped）。"""
    path = evidence_path(workspace, uid, phase)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _probe_video(path: Path) -> dict:
    """探测成片：只报**事实**，探测不到就留空（让 checks 记 WARN/FAIL，不猜）。"""
    out: dict = {"path": str(path), "exists": Path(path).is_file()}
    if not out["exists"]:
        return out
    out["bytes"] = Path(path).stat().st_size
    try:
        from ..tools import get_video_info
        info = get_video_info(str(path))
    except Exception as exc:      # noqa: BLE001 —— ffprobe 缺失/失败不该炸验片
        out["probe_error"] = f"{type(exc).__name__}: {exc}"
        return out
    streams = info.get("streams") or []
    out["video_streams"] = sum(1 for s in streams if s.get("codec_type") == "video")
    out["audio_streams"] = sum(1 for s in streams if s.get("codec_type") == "audio")
    fmt = info.get("format") or {}
    try:
        out["duration"] = round(float(fmt.get("duration") or 0.0), 2)
    except (TypeError, ValueError):
        out["duration"] = None
    return out


def _read_json(path: Path) -> dict:
    if not Path(path).is_file():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _spec_expectations(doc: dict) -> dict:
    """把 spec 里的"这条片应该长什么样"抽成 QA 期望值。"""
    story = doc.get("story_spec") or {}
    dna = (doc.get("creative") or {}).get("dna") or story.get("dna") or {}
    shots = story.get("shots") or []
    lines = story.get("lines") or []
    outside = "@elder_male" not in str(dna.get("cast_pattern") or "")
    return {
        "duration": doc.get("duration") or story.get("duration"),
        "dialogue_mode": dna.get("dialogue_mode") or story.get("dialogue_mode") or "",
        "products_expected": 1,
        "people_expected": len([s for s in str(dna.get("cast_pattern") or "").split("+") if s.strip()]),
        "shot_count": len(shots),
        "expected_lines": [
            {"shot": line.get("shot"), "speaker": line.get("speaker"), "text": line.get("text")}
            for line in lines if isinstance(line, dict) and str(line.get("text") or "").strip()
        ],
        "hook_type": dna.get("hook_type") or "",
        "outdoor": outside,
    }


def _spec_copy(doc: dict) -> dict:
    """spec 里**会对外出现**的文案（合规门只扫这些；制作说明不扫）。"""
    story = doc.get("story_spec") or {}
    dna = (doc.get("creative") or {}).get("dna") or {}
    spoken = " ".join(str(line.get("text") or "") for line in (story.get("lines") or [])
                      if isinstance(line, dict))
    return {"title": str(doc.get("title") or ""),
            "spoken": spoken,
            "on_screen": "",
            "description": " ".join(str(dna.get(k) or "") for k in ("payoff", "ending", "CTA"))}


def gather_evidence(workspace: Path, uid: str, doc: dict, *, phase: str = "gen") -> dict:
    """真实/Gate 环境下的证据收集（缺什么就少什么，不编造）。"""
    workspace = Path(workspace)
    ev = load_evidence(workspace, uid, phase)
    ev.setdefault("uid", uid)
    ev.setdefault("phase", phase)
    ev["video"] = {**_probe_video(video_path(workspace, uid, phase)), **(ev.get("video") or {})}
    ev["spec"] = {**_spec_expectations(doc), **(ev.get("spec") or {})}
    ev.setdefault("copy", _spec_copy(doc))
    if not ev.get("transcript"):
        tr = _read_json(workspace / TRANSCRIPT_FILENAME.get(phase, "").format(uid=uid))
        if tr:
            ev["transcript"] = tr
    return ev


class QaCritic:
    """无状态判定器：同一份证据一定得到同一份报告。"""

    name = "qa-critic/1.0"

    def analyze(self, evidence: dict, *, uid: str = "", stage: str = "qa",
                dimensions: tuple[str, ...] | None = None) -> QaReport:
        ev = dict(evidence or {})
        uid = uid or str(ev.get("uid") or "")
        findings, dims, notes = run_checks(ev, dimensions=dimensions)
        return QaReport(uid=uid, stage=stage, findings=findings, dimensions=dims,
                        coverage=coverage(dims), notes=notes,
                        generated_at=datetime.now().isoformat(timespec="seconds"))


def analyze(evidence: dict, *, uid: str = "", stage: str = "qa",
            dimensions: tuple[str, ...] | None = None) -> QaReport:
    return QaCritic().analyze(evidence, uid=uid, stage=stage, dimensions=dimensions)


def critique(workspace: Path, uid: str, doc: dict, *, phase: str = "gen",
             stage: str = "") -> QaReport:
    """一步到位：收集 + 判定（stage 直接用这个）。"""
    ev = gather_evidence(workspace, uid, doc, phase=phase)
    return analyze(ev, uid=uid, stage=stage or ("qa" if phase == "gen" else "compose"),
                   dimensions=PHASE_DIMENSIONS.get(phase, DIMENSIONS))
