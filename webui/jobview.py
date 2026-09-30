"""JobStore → WebUI 任务台视图（Phase 12）。

前端**不许猜状态**：这里的每个字段都从 canonical 事实投影出来 ——
`jobs / attempts / artifacts / events / evaluations / publishes / performance_metrics`
加上 Planner 落盘的 `state/creative/dna_<uid>.json` 与 packaging artifact。

设计约定：
  · 只读，不写任何表；
  · 缺失的信息一律为 `None`/空列表，不用默认值假装"有"；
  · `blocked` 块只在 FAILED/BLOCKED 出现，且必须带 `human_action`（为什么需要人工）。
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.jobstore import JobState
from lib.orchestrator.errors import (
    human_action_hint,
    is_retryable,
    repair_action_for,
)

# 允许的按钮：与 orchestrator.cancel_one / retry / resume 的守卫保持一致
CANCELLABLE: frozenset[str] = frozenset(
    set(JobState.ALL) - set(JobState.TERMINAL))
RETRYABLE: frozenset[str] = frozenset({JobState.FAILED, JobState.BLOCKED})
RESUMABLE: frozenset[str] = frozenset({JobState.PAUSED})
MATERIAL_STATES: tuple[str, ...] = (
    JobState.READY, JobState.PUBLISHING, JobState.LEARNING, JobState.DONE,
    JobState.PAUSED, JobState.BLOCKED, JobState.FAILED,
)

DNA_FILENAME = "dna_{uid}.json"

# performance_metrics 表里的真实指标列（缺失即 None，绝不用 0 顶替）
PERF_FIELDS: tuple[str, ...] = (
    "impressions", "views", "skip_2s", "retention_5s", "avg_watch_time", "avg_watch_pct",
    "completion", "rewatches", "likes", "comments", "shares", "saves", "follows",
    "profile_visits", "dms", "conversion_proxy",
)


def _dry_of(job: dict) -> bool | None:
    """dry 演练开关只认这次运行的 config_snapshot；没有快照就是 None（不猜）。"""
    snap = job.get("config_snapshot")
    if not snap:
        return None
    try:
        data = json.loads(snap) if isinstance(snap, str) else dict(snap)
    except (TypeError, ValueError):
        return None
    value = data.get("dry_mode")
    return None if value is None else bool(value)


def perf_view(row: dict) -> dict:
    """一条表现快照的投影：指标 + 非空指标数（前端不再自己数 key）。"""
    metrics = {k: row.get(k) for k in PERF_FIELDS}
    return {
        "platform": row.get("platform"),
        "post_id": row.get("post_id"),
        "snapshot_time": row.get("snapshot_time"),
        "metric_count": sum(1 for v in metrics.values() if v is not None),
        "metrics": metrics,
        "raw": row.get("raw"),
    }


def load_creative(state_dir: str | Path, uid: str) -> dict | None:
    """Planner 落盘的 CreativeDNA 文档（唯一事实来源）；没有就是 None。"""
    path = Path(state_dir) / "creative" / DNA_FILENAME.format(uid=uid)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    return {
        "structure": doc.get("structure") or "",
        "structure_name": doc.get("structure_name") or "",
        "day": doc.get("day") or "",
        "dna": doc.get("dna") or {},
        "rationale": doc.get("rationale") or {},
        "path": str(path),
    }


def _event_error_code(event: dict) -> str:
    """事件的错误码：优先列，其次 data（orchestrator 的 stage_failed 把码写在 data 里）。"""
    code = event.get("error_code")
    if code:
        return str(code)
    data = event.get("data")
    if isinstance(data, dict) and data.get("error_code"):
        return str(data["error_code"])
    return ""


def last_error(detail: dict) -> dict | None:
    """最后一条"说清为什么停在这里"的事件（带错误码，或就是那次 stage_failed）。"""
    for event in reversed(detail.get("events") or []):
        if _event_error_code(event):
            return event
        if str(event.get("type") or "") == "stage_failed":
            return event
    return None


def blocked_block(detail: dict, repairs: list[dict] | None = None) -> dict | None:
    """FAILED/BLOCKED 的人工原因：错误码 → 人话 + 下一步动作。"""
    job = detail.get("job") or {}
    status = str(job.get("status") or "")
    if status not in (JobState.BLOCKED, JobState.FAILED):
        return None
    event = last_error(detail) or {}
    code = (_event_error_code(event) or job.get("error_code")
            or ((repairs or [{}])[-1].get("error_code") if repairs else "") or "")
    message = str(event.get("message") or "")
    return {
        "code": code,
        "message": message,
        "human_action": human_action_hint(code, message),
        "next_action": repair_action_for(code) if code else "",
        "retryable": bool(code) and is_retryable(code),
        "at": event.get("created_at") or job.get("updated_at") or "",
        "stage": event.get("stage") or job.get("current_stage") or "",
    }


def qa_view(evaluations: list[dict]) -> dict:
    """质检摘要：只取 evaluations 里已存在的分数，缺就是 None。"""
    qa = [e for e in evaluations if str(e.get("kind") or "").startswith("qa")]
    latest = qa[-1] if qa else None
    scores = [e.get("score") for e in qa if e.get("score") is not None]
    return {
        "count": len(qa),
        "latest_kind": (latest or {}).get("kind"),
        "latest_score": (latest or {}).get("score"),
        "latest_passed": (None if latest is None or latest.get("passed") is None
                          else bool(latest.get("passed"))),
        "min_score": min(scores) if scores else None,
        "detail": (latest or {}).get("detail"),
    }


def job_summary(job: dict) -> dict:
    """任务台列表行（真实状态机字段，不做字符串包含判断）。"""
    status = str(job.get("status") or "")
    return {
        "uid": job.get("uid"),
        "goal": job.get("goal") or "",
        "status": status,
        "stage": job.get("current_stage") or "",
        "error_code": job.get("error_code") or "",
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "cost_spent": job.get("cost_spent"),
        "cost_estimate": job.get("cost_estimate"),
        "budget_cap": job.get("budget_cap"),
        "priority": job.get("priority"),
        "dry": _dry_of(job),
        "actions": {
            "cancel": status in CANCELLABLE,
            "retry": status in RETRYABLE,
            "resume": status in RESUMABLE,
        },
    }


def artifacts_view(store, uid: str) -> dict:
    job = store.get_job(uid)
    if job is None:
        return {"error": "任务不存在"}
    items = []
    for art in store.list_artifacts(uid):
        path = art.get("path")
        exists = bool(path) and Path(str(path)).is_file()
        items.append({
            "type": art.get("type"), "version": art.get("version"),
            "stage": art.get("stage"), "path": path, "bytes": art.get("bytes"),
            "sha256": art.get("sha256"), "meta": art.get("meta"),
            "created_at": art.get("created_at"), "exists": exists,
            "name": Path(str(path)).name if path else "",
        })
    return {"uid": uid, "count": len(items), "artifacts": items}


def events_view(store, uid: str, *, since: int = 0, limit: int = 200) -> dict:
    if store.get_job(uid) is None:
        return {"error": "任务不存在"}
    events = store.list_events(uid, limit=max(1, min(int(limit or 200), 1000)))
    if since:
        events = [e for e in events if int(e.get("id") or 0) > int(since)]
    return {"uid": uid, "count": len(events), "events": events,
            "last_id": max([int(e.get("id") or 0) for e in events] or [0])}


def detail_view(store, uid: str, *, state_dir: str | Path, out_dir: str | Path | None = None) -> dict | None:
    """完整任务详情：前端只需渲染，无需二次推断。"""
    detail = store.detail(uid)
    if not detail:
        return None
    job = detail["job"]
    artifacts = [
        {**art, "exists": bool(art.get("path")) and Path(str(art["path"])).is_file(),
         "name": Path(str(art.get("path"))).name if art.get("path") else ""}
        for art in detail.pop("artifacts") or []
    ]
    provider_tasks = store.list_provider_tasks(uid)
    repairs = store.list_repairs(uid)
    job_id = job.get("id")
    attempts = [
        {**att, "is_current": True} if att.get("job_id") == job_id else att
        for att in detail["attempts"]
    ]
    return {
        "job": job,
        "summary": job_summary(job),
        "creative": load_creative(state_dir, uid),
        "qa": qa_view(detail["evaluations"]),
        "evaluations": detail["evaluations"],
        "attempts": attempts,
        "provider_tasks": provider_tasks,
        "repairs": repairs,
        "repair_summary": store.repair_summary(uid),
        "artifacts": artifacts,
        "publishes": detail["publishes"],
        "performance": [perf_view(m) for m in store.list_performance_metrics(uid, limit=50)],
        "events": detail["events"],
        "blocked": blocked_block(detail, repairs),
    }


def _material_of(store, uid: str, *, state_dir: str | Path,
                 out_dir: str | Path | None = None) -> dict:
    """成片区一条：视频 + QA 摘要 + 标题/封面方案 + 发布状态 + 表现数据。"""
    detail = store.detail(uid) or {"job": store.get_job(uid) or {}}
    job = detail["job"]
    artifacts = store.list_artifacts(uid)
    videos = [a for a in artifacts if a.get("type") == "video"]
    finals = [a for a in artifacts if a.get("type") == "final"]
    video = (finals or videos)
    video_path = ""
    for art in reversed(video):
        if art.get("path") and Path(str(art["path"])).is_file():
            video_path = str(art["path"])
            break
    packaging = None
    for art in reversed(artifacts):
        if art.get("type") == "packaging" and art.get("path"):
            try:
                packaging = json.loads(Path(str(art["path"])).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                packaging = None
            break
    repairs = store.list_repairs(uid)
    publishes = store.list_publishes(uid)
    metrics = store.list_performance_metrics(uid, limit=10)
    return {
        "uid": uid,
        "goal": job.get("goal") or "",
        "status": job.get("status") or "",
        "stage": job.get("current_stage") or "",
        "updated_at": job.get("updated_at"),
        "cost_spent": job.get("cost_spent"),
        "video": video_path,
        "video_url": _media_url(out_dir, video_path),
        "creative": load_creative(state_dir, uid),
        "qa": qa_view(store.list_evaluations(uid)),
        "publish": [
            {"platform": p.get("platform"), "status": p.get("status"),
             "post_id": p.get("post_id"), "url": p.get("url"),
             "external_id": p.get("external_id"), "at": p.get("created_at")}
            for p in publishes
        ],
        "performance": perf_view(metrics[-1]) if metrics else None,
        "title": _packaging_title(packaging),
        "cover": _packaging_cover(packaging),
        "hashtags": list((packaging or {}).get("hashtags") or []),
        "blocked": blocked_block(detail, repairs),
    }


def _media_url(out_dir: str | Path | None, path: str) -> str:
    """本地文件 → `/media/...` URL（只在文件确实位于 out/ 下时给 URL）。"""
    if not path or not out_dir:
        return ""
    out = Path(out_dir)
    try:
        rel = Path(path).resolve().relative_to(out.resolve())
    except (OSError, ValueError):
        return ""
    return "/media/" + rel.as_posix()


def _packaging_title(packaging: dict | None) -> str:
    if not isinstance(packaging, dict):
        return ""
    chosen = packaging.get("chosen_title")
    if chosen:
        return str(chosen)
    for key in ("title", "titles"):
        value = packaging.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return str(first.get("title") or first.get("text") or "")
    candidates = packaging.get("title_candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict):
            return str(first.get("title") or first.get("text") or "")
        return str(first)
    return ""


def _packaging_cover(packaging: dict | None) -> str:
    if not isinstance(packaging, dict):
        return ""
    for key in ("cover_text", "cover", "cover_copy", "first_frame"):
        value = packaging.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def materials(store, *, state_dir: str | Path, out_dir: str | Path | None = None,
              limit: int = 12) -> list[dict]:
    """成片区：只列"已经出片/归档"的任务，按更新时间倒序。"""
    jobs = store.list_jobs(limit=max(1, min(int(limit or 12) * 4, 200)))
    out = []
    for job in jobs:
        if str(job.get("status")) not in MATERIAL_STATES:
            continue
        out.append(_material_of(store, str(job["uid"]), state_dir=state_dir,
                                out_dir=out_dir))
        if len(out) >= limit:
            break
    return out
