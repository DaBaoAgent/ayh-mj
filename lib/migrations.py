"""SQLite schema 版本化迁移（Phase 2）。

为什么不用 `CREATE TABLE IF NOT EXISTS`：
  它无法表达"给已有表加列/改语义"，会让不同机器上的 schema 静默漂移。
本模块把 schema 变成有序 migration：
  · 每个版本一个函数，按顺序应用，只应用一次，记录进 `schema_migrations`；
  · 应用前若旧库非空，先备份到 `state/backups/`（不删任何历史数据）；
  · 旧库（没有 `schema_migrations` 但已有 `jobs` 表）识别为 v1 基线，只补记不重跑。
"""
from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ── v1：既有基线 schema（与 Phase 0/1 的 init_db 完全一致）─────────────
V1_LEGACY_DDL = """
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    video_id TEXT NOT NULL UNIQUE,
    title TEXT,
    author TEXT,
    author_id TEXT,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    duration INTEGER,
    cover_url TEXT,
    video_url TEXT,
    keywords TEXT,
    score REAL,
    matched INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    trend_id INTEGER REFERENCES trends(id),
    status TEXT DEFAULT 'pending',
    script TEXT,
    script_word_count INTEGER,
    storyboard TEXT,
    shots TEXT,
    video_path TEXT,
    duration REAL,
    covers TEXT,
    publish_results TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS publishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    platform TEXT NOT NULL,
    post_id TEXT,
    post_url TEXT,
    status TEXT DEFAULT 'pending',
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    comment_id TEXT NOT NULL UNIQUE,
    comment_text TEXT,
    commenter TEXT,
    reply_text TEXT,
    reply_status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    replied_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trends_platform ON trends(platform);
CREATE INDEX IF NOT EXISTS idx_trends_score ON trends(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(uid);
"""

# ── v2：canonical job store（jobs 扩展 + attempts/artifacts/events/...）──
V2_CANONICAL_DDL = """
ALTER TABLE jobs ADD COLUMN goal TEXT;
ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 5;
ALTER TABLE jobs ADD COLUMN current_stage TEXT;
ALTER TABLE jobs ADD COLUMN error_code TEXT;
ALTER TABLE jobs ADD COLUMN cost_estimate REAL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN cost_spent REAL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN budget_cap REAL;
ALTER TABLE jobs ADD COLUMN config_snapshot TEXT;
ALTER TABLE jobs ADD COLUMN fingerprint TEXT;
ALTER TABLE jobs ADD COLUMN started_at TEXT;
ALTER TABLE jobs ADD COLUMN finished_at TEXT;
ALTER TABLE jobs ADD COLUMN pause_reason TEXT;

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    stage TEXT NOT NULL,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    provider TEXT,
    model TEXT,
    workflow TEXT,
    fingerprint TEXT,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    error_code TEXT,
    cost REAL DEFAULT 0,
    message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    type TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    stage TEXT,
    path TEXT,
    sha256 TEXT,
    bytes INTEGER,
    meta TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    stage TEXT,
    message TEXT,
    data TEXT
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    kind TEXT NOT NULL,
    score REAL,
    passed INTEGER,
    stage TEXT,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    platform TEXT NOT NULL,
    post_id TEXT,
    post_url TEXT,
    external_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    ai_disclosure TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    platform TEXT NOT NULL,
    post_id TEXT,
    snapshot_time TEXT NOT NULL,
    impressions INTEGER, views INTEGER, skip_2s INTEGER, retention_5s REAL,
    avg_watch_time REAL, avg_watch_pct REAL, completion REAL, rewatches INTEGER,
    likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER,
    follows INTEGER, profile_visits INTEGER, dms INTEGER, conversion_proxy REAL,
    raw TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_job ON attempts(job_id, stage);
CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id, type);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id, id);
CREATE INDEX IF NOT EXISTS idx_evaluations_job ON evaluations(job_id, kind);
CREATE INDEX IF NOT EXISTS idx_publish_records_job ON publish_records(job_id, platform);
CREATE UNIQUE INDEX IF NOT EXISTS idx_publish_records_ext
    ON publish_records(job_id, platform, external_id);
CREATE INDEX IF NOT EXISTS idx_perf_job ON performance_metrics(job_id, platform, snapshot_time);
"""

# 旧 status → canonical 状态（一次性兼容迁移；不删任何历史行）
LEGACY_STATUS_MAP = {
    "pending": "PLANNING",
    "trend": "RESEARCHING",
    "copy": "SCRIPTING",
    "storyboard": "PREFLIGHT",
    "generate": "GENERATING",
    "compose": "COMPOSING",
    "ready": "READY",
    "published": "DONE",
    "failed": "FAILED",
}


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def _v2(conn: sqlite3.Connection) -> None:
    conn.executescript(V2_CANONICAL_DDL)
    for legacy, canonical in LEGACY_STATUS_MAP.items():
        ids = [r[0] for r in conn.execute("SELECT id FROM jobs WHERE status = ?", (legacy,))]
        if not ids:
            continue
        conn.execute("UPDATE jobs SET status = ? WHERE status = ?", (canonical, legacy))
        now = datetime.now().isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO events (job_id, ts, type, message, data) VALUES (?, ?, ?, ?, ?)",
            [(jid, now, "migration", f"legacy status '{legacy}' → '{canonical}'",
              '{"migration": 2}') for jid in ids])
    conn.execute("UPDATE jobs SET current_stage = LOWER(status) WHERE current_stage IS NULL")


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "legacy_baseline", lambda conn: conn.executescript(V1_LEGACY_DDL)),
    Migration(2, "canonical_job_store", _v2),
)

SCHEMA_VERSION = MIGRATIONS[-1].version


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL
           )""")


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def applied_versions(conn: sqlite3.Connection) -> list[int]:
    ensure_migration_table(conn)
    return sorted(r[0] for r in conn.execute("SELECT version FROM schema_migrations"))


def current_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn)
    return versions[-1] if versions else 0


def pending_migrations(conn: sqlite3.Connection) -> list[Migration]:
    applied = set(applied_versions(conn))
    baseline = not applied and table_exists(conn, "jobs")
    out = []
    for mig in MIGRATIONS:
        if mig.version in applied:
            continue
        if baseline and mig.version == 1:
            continue  # 旧库已含 v1 schema，只补记
        out.append(mig)
    return out


def backup_db(db_path: Path, *, keep: int = 10) -> Path | None:
    """迁移前备份，返回备份路径（不存在或为空则返回 None）。"""
    db_path = Path(db_path)
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = backup_dir / f"{db_path.stem}_{stamp}{db_path.suffix}"
    shutil.copy2(db_path, dest)
    old = sorted(backup_dir.glob(f"{db_path.stem}_*{db_path.suffix}"))
    for stale in old[:-keep]:
        stale.unlink(missing_ok=True)
    return dest


def apply_migrations(conn: sqlite3.Connection, *, db_path: Path | None = None,
                     backup: bool = True) -> dict:
    """应用所有待执行 migration，返回 {applied, from_version, to_version, backup}。"""
    ensure_migration_table(conn)
    start_version = current_version(conn)
    pending = pending_migrations(conn)

    backup_path = None
    if pending and backup and db_path is not None:
        backup_path = backup_db(Path(db_path))

    if not pending:
        # 旧库首次接入：把 v1 基线补记进 schema_migrations
        if start_version == 0 and table_exists(conn, "jobs"):
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                (1, "legacy_baseline", datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        return {"applied": [], "from_version": start_version,
                "to_version": current_version(conn), "backup": None}

    applied: list[int] = []
    for mig in pending:
        mig.apply(conn)
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
            (mig.version, mig.name, datetime.now().isoformat(timespec="seconds")))
        applied.append(mig.version)
    conn.commit()
    return {"applied": applied, "from_version": start_version,
            "to_version": current_version(conn),
            "backup": str(backup_path) if backup_path else None}
