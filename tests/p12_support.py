"""Phase 12 测试共享工具 —— 在临时 state 上造 canonical 任务与全部事实源。

只做本地写库/写文件的事：不联网、不付费、不执行任何 stage。
造出来的任务一律带 `dry_mode=True` 的 config_snapshot —— 即使有代码去 resume/retry，
也只会走演练链路，不可能提交付费任务。
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.jobstore import JobState

LINEAR = tuple(JobState.LINEAR)
SIDE = tuple(JobState.SIDE)


def walk_to(store, uid: str, target: str) -> None:
    """沿 canonical 主线一步步 transition 到 target（不跳步，与状态机一致）。"""
    target = str(target).upper()
    job = store.get_job(uid)
    if job is None:
        raise KeyError(uid)
    if target in SIDE:
        if job["status"] in SIDE:
            return
        if job["status"] == JobState.PLANNING:
            walk_to(store, uid, JobState.GENERATING)
        store.transition(uid, target, stage=target.lower())
        return
    for name in LINEAR[: LINEAR.index(target) + 1]:
        if store.get_job(uid)["status"] == name:
            continue
        store.transition(uid, name, stage=name.lower())


def make_job(store, uid: str, *, goal: str = "", status: str = JobState.PLANNING,
             error_code: str | None = None, error_stage: str = "",
             error_message: str = "", dry: bool | None = True,
             cost_spent: float | None = None, budget_cap: float | None = None) -> str:
    """建一个 job；dry 默认 True（演练快照）。error_code 会写成真实的 stage_failed 事件。"""
    snapshot = {"dry_mode": bool(dry)} if dry is not None else None
    store.create_job(goal=goal, uid=uid, budget_cap=budget_cap, config_snapshot=snapshot)
    if str(status).upper() != JobState.PLANNING:
        walk_to(store, uid, status)
    if cost_spent is not None:
        store.add_cost(uid, cost_spent)
    if error_code:
        store.set_fields(uid, error_code=error_code)
        store.add_event(
            uid, "stage_failed",
            error_message or f"✗ {error_stage or 'stage'}：{error_code}",
            stage=error_stage or None, data={"error_code": error_code})
    return uid


def add_artifact(store, uid: str, type_: str, name: str | None = None, *,
                 root: str | Path | None = None, content: bytes | str = b"x",
                 stage: str = ""):
    """登记产物；给了 root+name 就真的落一份文件（用于 exists / /media URL 断言）。"""
    path = None
    if root is not None and name:
        path = Path(root) / "out" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else str(content).encode("utf-8"))
    return store.add_artifact(uid, type_, path, stage=stage or None)


def add_qa(store, uid: str, *, kind: str = "qa_critic", score: float = 0.9,
           passed: bool = True, stage: str = "qa", detail: dict | None = None):
    return store.add_evaluation(uid, kind, score=score, passed=passed, stage=stage,
                                detail=detail or {"checks": ["ok"]})


def add_attempt(store, uid: str, stage: str = "generate", *, attempt_no: int | None = None,
                provider: str = "autodl", model: str = "h3", workflow: str = "w15",
                fingerprint: str = "fp", status: str = "SUCCESS", cost: float = 0.0,
                error_code: str | None = None, message: str = "") -> int:
    attempt_id = store.record_attempt(uid, stage, attempt_no=attempt_no, provider=provider,
                                      model=model, workflow=workflow, fingerprint=fingerprint)
    store.finish_attempt(attempt_id, status, error_code=error_code, cost=cost, message=message)
    return attempt_id


def add_repair(store, uid: str, *, error_code: str, action: str = "REGENERATE_SHOT",
               stage: str = "generate", status: str = "DONE", cost: float = 0.0,
               rewind_to: str = "", attempt: int = 1, detail: dict | None = None) -> int:
    return store.add_repair(uid, error_code=error_code, action=action, stage=stage,
                            status=status, cost=cost, rewind_to=rewind_to, attempt=attempt,
                            detail=detail or {"reason": "测试夹具"})


def add_publish(store, uid: str, platform: str = "douyin", *, status: str = "DRAFT",
                post_id: str | None = None, external_id: str | None = None,
                ai_disclosure: str | None = None) -> int:
    return store.record_publish(uid, platform, post_id=post_id, external_id=external_id,
                                status=status, ai_disclosure=ai_disclosure)


def add_performance(store, uid: str, platform: str = "douyin", *,
                    snapshot_time: str | None = None, **metrics) -> int:
    return store.add_performance_metric(uid, platform, snapshot_time=snapshot_time, **metrics)


def write_dna(root: str | Path, uid: str, structure_id: str = "S_duo_conflict", *,
              day: str = "2026-09-30", **overrides) -> Path:
    """在 state 目录下写一份 DNA 文档（与 Planner 落盘同口径）。root 就是 state 目录。"""
    path = Path(root) / "creative" / f"dna_{uid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    dna = {"genre": "G1", "hook_type": "冲突开场", "shot_pattern": "4镜对撞",
           "angle": "日常场景", "sales_point": "单手提起",
           "audience": "子女代购决策者", "risk_flags": []}
    dna.update(overrides)
    path.write_text(json.dumps({
        "uid": uid, "day": day, "structure": structure_id,
        "structure_name": "双人对撞", "dna": dna, "scores": {}, "rationale": {},
        "claim_ids": [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def apply_spec(store, state_dir: str | Path, spec: dict) -> str:
    """按一份 JSON spec 造一个完整任务（供 seed 脚本与测试共用）。"""
    uid = str(spec["uid"])
    make_job(store, uid, goal=spec.get("goal", ""), status=spec.get("status", JobState.READY),
             error_code=spec.get("error_code"), error_stage=spec.get("error_stage", ""),
             error_message=spec.get("error_message", ""), dry=spec.get("dry", True),
             cost_spent=spec.get("cost_spent"), budget_cap=spec.get("budget_cap"))
    creative = spec.get("creative")
    if creative:
        structure = creative.get("structure", "S_duo_conflict")
        overrides = {k: v for k, v in creative.items() if k not in ("structure", "day")}
        write_dna(state_dir, uid, structure, day=creative.get("day", "2026-09-30"),
                  **overrides)
    for art in spec.get("artifacts", []):
        add_artifact(store, uid, art.get("type", "final"), art.get("name"),
                     root=Path(state_dir).parent, content=art.get("content", b"video-bytes"),
                     stage=art.get("stage", ""))
    for qa in spec.get("qa", []):
        add_qa(store, uid, kind=qa.get("kind", "qa_critic"), score=qa.get("score", 0.9),
               passed=qa.get("passed", True), stage=qa.get("stage", "qa"),
               detail=qa.get("detail"))
    for attempt in spec.get("attempts", []):
        add_attempt(store, uid, attempt.get("stage", "generate"),
                    provider=attempt.get("provider", "autodl"),
                    workflow=attempt.get("workflow", "w15"),
                    status=attempt.get("status", "SUCCESS"),
                    cost=attempt.get("cost", 0.0), error_code=attempt.get("error_code"))
    for repair in spec.get("repairs", []):
        add_repair(store, uid, error_code=repair.get("error_code", "VISUAL_QA_FAIL"),
                   action=repair.get("action", "REGENERATE_SHOT"),
                   stage=repair.get("stage", "generate"),
                   status=repair.get("status", "DONE"), cost=repair.get("cost", 0.0))
    for pub in spec.get("publishes", []):
        add_publish(store, uid, pub.get("platform", "douyin"), status=pub.get("status", "DRAFT"),
                    post_id=pub.get("post_id"), external_id=pub.get("external_id"),
                    ai_disclosure=pub.get("ai_disclosure"))
    for perf in spec.get("performance", []):
        metrics = perf.get("metrics", {k: v for k, v in perf.items() if k != "platform"})
        add_performance(store, uid, perf.get("platform", "douyin"), **metrics)
    return uid
