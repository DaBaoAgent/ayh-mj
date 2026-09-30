"""Canonical JobStore + 任务状态机（Phase 2）。

唯一事实源：`state/pipeline.db`。
  · 任务状态只能通过 `JobStore.transition()` 修改，非法转换会被拒绝并写明原因；
  · 每次状态转换、每次 provider 尝试、每个 artifact、每条评分与发布结果都落表；
  · queue JSON 只是 artifact/dispatch 缓存，删掉它不会丢任务事实。

状态机（canonical，UPPERCASE）：
    PLANNING → RESEARCHING → SCRIPTING → PREFLIGHT → GENERATING → QA
             → REPAIRING → COMPOSING → PACKAGING → READY → PUBLISHING
             → LEARNING → DONE
旁路：PAUSED / BLOCKED / FAILED / CANCELLED
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any


class JobState:
    """canonical 状态常量与顺序。"""

    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    SCRIPTING = "SCRIPTING"
    PREFLIGHT = "PREFLIGHT"
    GENERATING = "GENERATING"
    QA = "QA"
    REPAIRING = "REPAIRING"
    COMPOSING = "COMPOSING"
    PACKAGING = "PACKAGING"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    LEARNING = "LEARNING"
    DONE = "DONE"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    LINEAR = (PLANNING, RESEARCHING, SCRIPTING, PREFLIGHT, GENERATING, QA,
              REPAIRING, COMPOSING, PACKAGING, READY, PUBLISHING, LEARNING, DONE)
    SIDE = (PAUSED, BLOCKED, FAILED, CANCELLED)
    ALL = LINEAR + SIDE
    TERMINAL = (DONE, CANCELLED)


ALL_STATES: tuple[str, ...] = JobState.ALL
LINEAR_STATES: tuple[str, ...] = JobState.LINEAR

# 旧 status/中文 → canonical（兼容既有调用方与历史数据）
STATUS_ALIASES: dict[str, str] = {
    "pending": JobState.PLANNING,
    "trend": JobState.RESEARCHING,
    "copy": JobState.SCRIPTING,
    "storyboard": JobState.PREFLIGHT,
    "generate": JobState.GENERATING,
    "compose": JobState.COMPOSING,
    "ready": JobState.READY,
    "published": JobState.DONE,
    "failed": JobState.FAILED,
}

_LINEAR_INDEX = {name: i for i, name in enumerate(JobState.LINEAR)}


def _build_transitions() -> dict[str, set[str]]:
    t: dict[str, set[str]] = {}
    for name in JobState.LINEAR:
        nxt: set[str] = set(JobState.SIDE)
        idx = _LINEAR_INDEX[name]
        if idx + 1 < len(JobState.LINEAR):
            nxt.add(JobState.LINEAR[idx + 1])
        # QA 通过时可直接进入 COMPOSING（跳过 REPAIRING），仍在"向前"语义内
        if name == JobState.QA:
            nxt.add(JobState.COMPOSING)
        # REPAIRING（Phase 8）是定点修复中枢：
        #   ① 任何"还没出片"的阶段都能把任务交给它（发现不合格 → 去修）；
        #   ② 它自己允许**回退**到更早阶段重做（重生成 / 重建字幕）。
        # 回退因此仍是合法转换，不需要 force 绕过状态机。
        if name != JobState.REPAIRING and idx < _LINEAR_INDEX[JobState.READY]:
            nxt.add(JobState.REPAIRING)
        if name == JobState.REPAIRING:
            nxt |= set(JobState.LINEAR[:idx])
        t[name] = nxt
    # 旁路状态可以恢复到任意"未终结"主线状态，也可以继续取消（人工终止意图永远有效）
    resume = set(JobState.LINEAR) - {JobState.DONE}
    for name in JobState.SIDE:
        t[name] = set() if name == JobState.CANCELLED else (resume | {JobState.CANCELLED})
    # DONE 是终点（仅允许重新打开为 PAUSED/FAILED 之类的人工操作 → 不再放行）
    t[JobState.DONE] = set()
    return t


TRANSITIONS: dict[str, set[str]] = _build_transitions()


class InvalidTransition(ValueError):
    """非法状态转换。"""


def normalize_state(value: str) -> str:
    """把任意写法（旧 status / 小写 / 中文别名）归一成 canonical 状态。"""
    if value is None:
        raise ValueError("状态不能为空")
    raw = str(value).strip()
    if raw in TRANSITIONS:
        return raw
    upper = raw.upper().replace(" ", "_").replace("-", "_")
    if upper in TRANSITIONS:
        return upper
    if raw.lower() in STATUS_ALIASES:
        return STATUS_ALIASES[raw.lower()]
    if upper in STATUS_ALIASES:
        return STATUS_ALIASES[upper]
    raise ValueError(f"未知状态: {value!r}（可用: {', '.join(JobState.ALL)}）")


def try_normalize_state(value: str) -> str | None:
    try:
        return normalize_state(value)
    except ValueError:
        return None


def can_transition(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, set())


def transition_error(src: str, dst: str) -> str:
    allowed = sorted(TRANSITIONS.get(src, set()))
    return (f"非法状态转换: {src} → {dst}；{src} 只允许转到 "
            f"{', '.join(allowed) if allowed else '（终态，不可再转）'}")


def utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class JobStore:
    """canonical 任务仓库。所有写操作都必须走这里。"""

    def __init__(self, connect_factory=None) -> None:
        self._connect_factory = connect_factory

    # ── 连接 ────────────────────────────────────────────────────
    def _connect(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        from .state import connect
        return connect()

    # ── jobs ───────────────────────────────────────────────────
    def create_job(self, goal: str = "", *, trend_id: int | None = None,
                   priority: int = 5, budget_cap: float | None = None,
                   config_snapshot: dict | None = None,
                   status: str = JobState.PLANNING, uid: str | None = None,
                   fingerprint: str | None = None) -> str:
        state = normalize_state(status)
        if uid is None:
            uid = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        snapshot = json.dumps(config_snapshot, ensure_ascii=False) if config_snapshot else None
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (uid, trend_id, status, current_stage, goal, priority, budget_cap,
                    config_snapshot, fingerprint, cost_estimate, cost_spent,
                    created_at, updated_at, started_at)
                   VALUES (?,?,?,?,?,?,?,?,?,0,0,?,?,?)""",
                (uid, trend_id, state, state.lower(), goal, priority, budget_cap,
                 snapshot, fingerprint, utc_now(), utc_now(), utc_now()))
            job_id = conn.execute("SELECT id FROM jobs WHERE uid = ?", (uid,)).fetchone()[0]
            self._insert_event(conn, job_id, "created", to_status=state, stage=state.lower(),
                               message=f"任务创建（{state}）")
            conn.commit()
        return uid

    def get_job(self, uid: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE uid = ?", (uid,)).fetchone()
            return dict(row) if row else None

    def get_job_by_id(self, job_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, status: str | None = None, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            if status:
                normalized = try_normalize_state(status) or status
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                    (normalized, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
                    (limit,)).fetchall()
            return [dict(r) for r in rows]

    def _job_id(self, conn: sqlite3.Connection, uid: str) -> int:
        row = conn.execute("SELECT id FROM jobs WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            raise KeyError(f"任务不存在: {uid}")
        return int(row[0])

    def transition(self, uid: str, to_status: str, *, stage: str | None = None,
                   message: str = "", actor: str = "system",
                   error_code: str | None = None, event_type: str = "status_change",
                   data: dict | None = None, force: bool = False) -> dict:
        """状态转换（唯一合法入口）。非法转换抛 InvalidTransition 并写明原因。"""
        target = normalize_state(to_status)
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            current = normalize_state(row[0]) if row and row[0] else JobState.PLANNING
            if current != target and not force and not can_transition(current, target):
                raise InvalidTransition(transition_error(current, target))

            fields = ["status = ?", "updated_at = ?"]
            values: list[Any] = [target, utc_now()]
            if stage:
                fields.append("current_stage = ?")
                values.append(stage)
            else:
                fields += ["current_stage = ?"]
                values.append(target.lower())
            if error_code is not None:
                fields.append("error_code = ?")
                values.append(error_code)
            if target in JobState.TERMINAL:
                fields.append("finished_at = ?")
                values.append(utc_now())
            if target == JobState.DONE:
                fields.append("published_at = COALESCE(published_at, ?)")
                values.append(utc_now())
            values.append(job_id)
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
            self._insert_event(
                conn, job_id, event_type, from_status=current, to_status=target,
                stage=stage or target.lower(),
                message=message or f"{current} → {target}（{actor}）",
                data={"actor": actor, **(data or {})})
            conn.commit()
            out = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(out)

    _FIELD_WHITELIST = {
        "trend_id", "script", "script_word_count", "storyboard", "shots", "video_path",
        "duration", "covers", "publish_results", "goal", "priority", "error_code",
        "cost_estimate", "cost_spent", "budget_cap", "fingerprint", "pause_reason",
        "config_snapshot",
    }

    def set_fields(self, uid: str, **kwargs) -> None:
        """更新非状态字段（白名单）。状态必须用 transition()。"""
        if "status" in kwargs:
            raise ValueError("状态必须通过 JobStore.transition() 修改，不能走 set_fields()")
        bad = set(kwargs) - self._FIELD_WHITELIST
        if bad:
            raise ValueError(f"set_fields 不允许的字段: {bad}（白名单: {sorted(self._FIELD_WHITELIST)}）")
        if not kwargs:
            return
        kwargs["updated_at"] = utc_now()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {sets} WHERE uid = ?", [*kwargs.values(), uid])
            conn.commit()

    def add_cost(self, uid: str, amount: float) -> float:
        """累加已发生成本，返回累计值。"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET cost_spent = COALESCE(cost_spent, 0) + ?, updated_at = ? WHERE uid = ?",
                (float(amount), utc_now(), uid))
            conn.commit()
            row = conn.execute("SELECT COALESCE(cost_spent, 0) FROM jobs WHERE uid = ?",
                               (uid,)).fetchone()
            return float(row[0]) if row else 0.0

    # ── events ─────────────────────────────────────────────────
    @staticmethod
    def _insert_event(conn: sqlite3.Connection, job_id: int, type_: str, *,
                      from_status: str | None = None, to_status: str | None = None,
                      stage: str | None = None, message: str = "",
                      data: dict | None = None) -> int:
        cur = conn.execute(
            """INSERT INTO events (job_id, ts, type, from_status, to_status, stage, message, data)
               VALUES (?,?,?,?,?,?,?,?)""",
            (job_id, utc_now(), type_, from_status, to_status, stage, message,
             json.dumps(data, ensure_ascii=False) if data else None))
        return int(cur.lastrowid)

    def add_event(self, uid: str, type_: str, message: str = "", *,
                  stage: str | None = None, data: dict | None = None) -> int:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            event_id = self._insert_event(conn, job_id, type_, stage=stage,
                                          message=message, data=data)
            conn.commit()
            return event_id

    def list_events(self, uid: str, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            rows = conn.execute(
                "SELECT * FROM events WHERE job_id = ? ORDER BY id ASC LIMIT ?",
                (job_id, limit)).fetchall()
            return [_decode(r, "data") for r in rows]

    def recent_events(self, after_id: int = 0, limit: int = 200) -> list[dict]:
        """全库事件流（带 uid）——SSE / 控制台不再猜阶段，直接读事实源。"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT e.id, e.ts, e.type, e.from_status, e.to_status, e.stage,
                          e.message, e.data, j.uid
                   FROM events e JOIN jobs j ON j.id = e.job_id
                   WHERE e.id > ? ORDER BY e.id ASC LIMIT ?""",
                (int(after_id), int(limit))).fetchall()
            return [_decode(r, "data") for r in rows]

    def max_event_id(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
            return int(row[0]) if row else 0

    # ── attempts ───────────────────────────────────────────────
    def record_attempt(self, uid: str, stage: str, *, attempt_no: int | None = None,
                       provider: str = "", model: str = "", workflow: str = "",
                       fingerprint: str = "") -> int:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            if attempt_no is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(attempt_no), 0) FROM attempts WHERE job_id = ? AND stage = ?",
                    (job_id, stage)).fetchone()
                attempt_no = int(row[0]) + 1
            cur = conn.execute(
                """INSERT INTO attempts
                   (job_id, stage, attempt_no, provider, model, workflow, fingerprint,
                    status, cost, started_at)
                   VALUES (?,?,?,?,?,?,?,'RUNNING',0,?)""",
                (job_id, stage, attempt_no, provider, model, workflow, fingerprint, utc_now()))
            conn.commit()
            return int(cur.lastrowid)

    def finish_attempt(self, attempt_id: int, status: str, *, error_code: str | None = None,
                       cost: float = 0.0, message: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE attempts SET status = ?, error_code = ?, cost = ?,
                   message = ?, finished_at = ? WHERE id = ?""",
                (status, error_code, float(cost), message, utc_now(), attempt_id))
            conn.commit()

    def list_attempts(self, uid: str) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            rows = conn.execute(
                "SELECT * FROM attempts WHERE job_id = ? ORDER BY id ASC", (job_id,)).fetchall()
            return [dict(r) for r in rows]

    # ── repairs（Phase 8：定点修复的次数/成本/结果，审计"为什么又跑了一遍"）──
    def add_repair(self, uid: str, *, error_code: str, action: str, stage: str = "",
                   rewind_to: str = "", target_shot: int | None = None, attempt: int = 1,
                   budget: int = 0, cost: float = 0.0, status: str = "PLANNED",
                   detail: dict | str | None = None) -> int:
        payload = detail if isinstance(detail, str) or detail is None else json.dumps(
            detail, ensure_ascii=False)
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            cur = conn.execute(
                """INSERT INTO repairs
                   (job_id, stage, error_code, action, rewind_to, target_shot, attempt,
                    budget, cost, status, detail, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, stage, error_code, action, rewind_to, target_shot, int(attempt),
                 int(budget), float(cost), status, payload, utc_now()))
            conn.commit()
            return int(cur.lastrowid)

    def update_repair(self, repair_id: int, *, cost: float | None = None,
                      status: str | None = None, detail: dict | str | None = None) -> bool:
        """回填一次修复的**真实成本/结果**（次数在 add 时落库，成本要等重跑完才知道）。"""
        sets: list[str] = []
        params: list = []
        if cost is not None:
            sets.append("cost = ?")
            params.append(float(cost))
        if status is not None:
            sets.append("status = ?")
            params.append(str(status))
        if detail is not None:
            payload = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
            sets.append("detail = ?")
            params.append(payload)
        if not sets:
            return False
        params.append(int(repair_id))
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE repairs SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()
            return cur.rowcount > 0

    def list_repairs(self, uid: str) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            rows = conn.execute(
                "SELECT * FROM repairs WHERE job_id = ? ORDER BY id ASC", (job_id,)).fetchall()
            return [_decode(r, "detail") for r in rows]

    def repair_summary(self, uid: str) -> dict:
        """修复次数 / 成本 / 最后一次结果 —— plan 阶段与最终验收都要用。"""
        rows = self.list_repairs(uid)
        by_code: dict[str, int] = {}
        for row in rows:
            code = str(row.get("error_code") or "")
            by_code[code] = by_code.get(code, 0) + 1
        return {"count": len(rows), "cost": round(sum(float(r.get("cost") or 0) for r in rows), 4),
                "by_code": by_code, "by_action": (rows[-1]["action"] if rows else None),
                "last": dict(rows[-1]) if rows else None}

    # ── provider tasks（幂等：先落 task_id 再轮询，Phase 4）────────
    def upsert_provider_task(self, uid: str, fingerprint: str, *, stage: str = "generate",
                             provider: str = "", workflow: str = "",
                             task_id: str | None = None, status: str = "SUBMITTED",
                             result_url: str | None = None, output_path: str | None = None,
                             cost: float | None = None, error_code: str | None = None,
                             bump_attempts: bool = False) -> int:
        """登记/更新 provider 任务（job+fingerprint 唯一）。提交拿到 task_id 后**立即**调用。"""
        now = utc_now()
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            conn.execute(
                """INSERT INTO provider_tasks
                   (job_id, fingerprint, stage, provider, workflow, task_id, status,
                    result_url, output_path, cost, attempts, error_code, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(job_id, fingerprint) DO UPDATE SET
                     task_id = COALESCE(excluded.task_id, provider_tasks.task_id),
                     status = excluded.status,
                     result_url = COALESCE(excluded.result_url, provider_tasks.result_url),
                     output_path = COALESCE(excluded.output_path, provider_tasks.output_path),
                     cost = MAX(COALESCE(excluded.cost, 0), COALESCE(provider_tasks.cost, 0)),
                     workflow = COALESCE(NULLIF(excluded.workflow, ''), provider_tasks.workflow),
                     error_code = excluded.error_code,
                     attempts = provider_tasks.attempts + ?,
                     updated_at = excluded.updated_at""",
                (job_id, fingerprint, stage, provider, workflow, task_id, status,
                 result_url, output_path, float(cost or 0.0), 1, error_code, now, now,
                 1 if bump_attempts else 0))
            conn.commit()
            row = conn.execute(
                "SELECT id FROM provider_tasks WHERE job_id=? AND fingerprint=?",
                (job_id, fingerprint)).fetchone()
            return int(row[0]) if row else 0

    def find_provider_task(self, uid: str, fingerprint: str | None = None, *,
                           task_id: str | None = None, stage: str | None = None) -> dict | None:
        """按 fingerprint（首选）或 task_id 查已提交任务；命中即"只 query，不重提交"。"""
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            if fingerprint:
                row = conn.execute(
                    "SELECT * FROM provider_tasks WHERE job_id=? AND fingerprint=?",
                    (job_id, fingerprint)).fetchone()
            elif task_id:
                row = conn.execute(
                    "SELECT * FROM provider_tasks WHERE job_id=? AND task_id=? "
                    "ORDER BY id DESC LIMIT 1", (job_id, task_id)).fetchone()
            elif stage:
                row = conn.execute(
                    "SELECT * FROM provider_tasks WHERE job_id=? AND stage=? "
                    "ORDER BY id DESC LIMIT 1", (job_id, stage)).fetchone()
            else:
                row = None
            return dict(row) if row else None

    def list_provider_tasks(self, uid: str, stage: str | None = None) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            if stage:
                rows = conn.execute(
                    "SELECT * FROM provider_tasks WHERE job_id=? AND stage=? ORDER BY id ASC",
                    (job_id, stage)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM provider_tasks WHERE job_id=? ORDER BY id ASC",
                    (job_id,)).fetchall()
            return [dict(r) for r in rows]

    def finish_provider_task(self, uid: str, fingerprint: str, *, status: str,
                             result_url: str | None = None, output_path: str | None = None,
                             cost: float | None = None,
                             error_code: str | None = None) -> None:
        """记录 provider 任务的终态（SUCCEEDED / FAILED / DOWNLOADING / DONE）。"""
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            conn.execute(
                """UPDATE provider_tasks SET
                     status = ?, result_url = COALESCE(?, result_url),
                     output_path = COALESCE(?, output_path),
                     cost = MAX(COALESCE(?, 0), COALESCE(cost, 0)),
                     error_code = ?, updated_at = ?
                   WHERE job_id = ? AND fingerprint = ?""",
                (status, result_url, output_path, cost, error_code, utc_now(),
                 job_id, fingerprint))
            conn.commit()

    # ── artifacts ──────────────────────────────────────────────
    def add_artifact(self, uid: str, type_: str, path: str | Path | None = None, *,
                     stage: str | None = None, version: int | None = None,
                     sha256: str | None = None, meta: dict | None = None) -> int:
        p = Path(path) if path is not None else None
        size = p.stat().st_size if p is not None and p.is_file() else None
        digest = sha256
        if digest is None and p is not None and p.is_file():
            digest = sha256_of(p.read_bytes())
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            if version is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM artifacts WHERE job_id = ? AND type = ?",
                    (job_id, type_)).fetchone()
                version = int(row[0]) + 1
            cur = conn.execute(
                """INSERT INTO artifacts
                   (job_id, type, version, stage, path, sha256, bytes, meta, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (job_id, type_, version, stage, str(p) if p is not None else None,
                 digest, size, json.dumps(meta, ensure_ascii=False) if meta else None,
                 utc_now()))
            conn.commit()
            return int(cur.lastrowid)

    def list_artifacts(self, uid: str, type_: str | None = None) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            if type_:
                rows = conn.execute(
                    "SELECT * FROM artifacts WHERE job_id = ? AND type = ? ORDER BY id ASC",
                    (job_id, type_)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM artifacts WHERE job_id = ? ORDER BY id ASC", (job_id,)).fetchall()
            return [_decode(r, "meta") for r in rows]

    # ── evaluations ────────────────────────────────────────────
    def add_evaluation(self, uid: str, kind: str, *, score: float | None = None,
                       passed: bool | None = None, stage: str | None = None,
                       detail: dict | str | None = None) -> int:
        payload = detail if isinstance(detail, str) or detail is None else json.dumps(
            detail, ensure_ascii=False)
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            cur = conn.execute(
                """INSERT INTO evaluations (job_id, kind, score, passed, stage, detail, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (job_id, kind, score, None if passed is None else int(passed),
                 stage, payload, utc_now()))
            conn.commit()
            return int(cur.lastrowid)

    def list_evaluations(self, uid: str, kind: str | None = None) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            if kind:
                rows = conn.execute(
                    "SELECT * FROM evaluations WHERE job_id = ? AND kind = ? ORDER BY id ASC",
                    (job_id, kind)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evaluations WHERE job_id = ? ORDER BY id ASC", (job_id,)).fetchall()
            return [_decode(r, "detail") for r in rows]

    # ── publish records ────────────────────────────────────────
    def record_publish(self, uid: str, platform: str, *, post_id: str | None = None,
                       post_url: str | None = None, external_id: str | None = None,
                       status: str = "PENDING", ai_disclosure: str | None = None,
                       error: str | None = None) -> int:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            conn.execute(
                """INSERT INTO publish_records
                   (job_id, platform, post_id, post_url, external_id, status,
                    ai_disclosure, error, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(job_id, platform, external_id) DO UPDATE SET
                     post_id = excluded.post_id, post_url = excluded.post_url,
                     status = excluded.status, ai_disclosure = excluded.ai_disclosure,
                     error = excluded.error, updated_at = excluded.updated_at""",
                (job_id, platform, post_id, post_url, external_id, status,
                 ai_disclosure, error, utc_now(), utc_now()))
            conn.commit()
            row = conn.execute(
                "SELECT id FROM publish_records WHERE job_id=? AND platform=? AND external_id IS ?",
                (job_id, platform, external_id)).fetchone()
            return int(row[0]) if row else 0

    def list_publishes(self, uid: str) -> list[dict]:
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            rows = conn.execute(
                "SELECT * FROM publish_records WHERE job_id = ? ORDER BY id ASC", (job_id,)).fetchall()
            return [dict(r) for r in rows]

    # ── performance metrics（Phase 11 学习层预留）────────────────
    def add_performance_metric(self, uid: str, platform: str, *,
                               post_id: str | None = None, snapshot_time: str | None = None,
                               raw: dict | None = None, **metrics: Any) -> int:
        cols = ["impressions", "views", "skip_2s", "retention_5s", "avg_watch_time",
                "avg_watch_pct", "completion", "rewatches", "likes", "comments",
                "shares", "saves", "follows", "profile_visits", "dms", "conversion_proxy"]
        unknown = set(metrics) - set(cols)
        if unknown:
            raise ValueError(f"未知指标: {unknown}（可用: {cols}）")
        values = [metrics.get(c) for c in cols]
        with self._connect() as conn:
            job_id = self._job_id(conn, uid)
            cur = conn.execute(
                f"""INSERT INTO performance_metrics
                    (job_id, platform, post_id, snapshot_time, {', '.join(cols)}, raw, created_at)
                    VALUES (?,?,?,?,{', '.join('?' * len(cols))},?,?)""",
                (job_id, platform, post_id, snapshot_time or utc_now(),
                 *values, json.dumps(raw, ensure_ascii=False) if raw else None, utc_now()))
            conn.commit()
            return int(cur.lastrowid)

    def list_performance_metrics(self, uid: str | None = None, *, platform: str | None = None,
                                 since: str | None = None,
                                 limit: int | None = None) -> list[dict]:
        """读取表现快照（Phase 11 学习层，只读）。

        缺失字段在行里就是 None —— 上层据此知道"平台没给这个数"，不必也不许拿 0 顶替。
        """
        sql = ["SELECT pm.*, j.uid AS job_uid FROM performance_metrics pm",
               "JOIN jobs j ON j.id = pm.job_id"]
        where: list[str] = []
        args: list = []
        if uid:
            where.append("j.uid = ?")
            args.append(uid)
        if platform:
            where.append("pm.platform = ?")
            args.append(platform)
        if since:
            where.append("pm.snapshot_time >= ?")
            args.append(since)
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY pm.snapshot_time ASC, pm.id ASC")
        if limit:
            sql.append("LIMIT ?")
            args.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(" ".join(sql), args).fetchall()
        return [_decode(r, "raw") for r in rows]

    # ── 聚合读取 ───────────────────────────────────────────────
    def detail(self, uid: str) -> dict | None:
        """完整任务视图（job + attempts + artifacts + events + evaluations + publishes）。"""
        job = self.get_job(uid)
        if job is None:
            return None
        return {
            "job": job,
            "attempts": self.list_attempts(uid),
            "artifacts": self.list_artifacts(uid),
            "events": self.list_events(uid),
            "evaluations": self.list_evaluations(uid),
            "publishes": self.list_publishes(uid),
        }

    def counts(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            by_status = {r[0]: r[1] for r in conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status")}
            return {"total": total, "by_status": by_status}


def _decode(row: sqlite3.Row, json_col: str) -> dict:
    out = dict(row)
    raw = out.get(json_col)
    if raw:
        with suppress(TypeError, ValueError):
            out[json_col] = json.loads(raw)
    return out


store = JobStore()
