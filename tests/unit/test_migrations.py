"""schema migration 回归（Phase 2）。

覆盖验收标准：
  · 空库可迁移到当前 schema 版本；
  · 迁移幂等（重复运行不再动 schema）；
  · 已有数据的老库迁移前自动备份、迁移后旧状态被一次性兼容映射、历史行不丢；
  · 备份文件按数量滚动清理。

Phase 4 追加：v3 提供 provider task 幂等表（先落 task_id 再轮询）。
"""
from __future__ import annotations

import sqlite3

import pytest

from lib import migrations

pytestmark = pytest.mark.unit


def _conn(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _make_legacy_db(path) -> None:
    conn = _conn(path)
    conn.executescript(migrations.V1_LEGACY_DDL)
    conn.execute("INSERT INTO trends (platform, video_id, title) VALUES ('douyin','v1','旧热点')")
    rows = [
        ("job_legacy_pending", "pending"),
        ("job_legacy_trend", "trend"),
        ("job_legacy_generate", "generate"),
        ("job_legacy_ready", "ready"),
        ("job_legacy_published", "published"),
        ("job_legacy_failed", "failed"),
    ]
    conn.executemany("INSERT INTO jobs (uid, trend_id, status) VALUES (?, 1, ?)", rows)
    conn.commit()
    conn.close()


def test_empty_db_migrates_to_current_version(tmp_path):
    db = tmp_path / "empty.db"
    conn = _conn(db)
    result = migrations.apply_migrations(conn, db_path=db)
    assert result["applied"] == [1, 2, 3, 4]
    assert migrations.current_version(conn) == migrations.SCHEMA_VERSION
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("jobs", "attempts", "artifacts", "events", "evaluations",
              "publish_records", "performance_metrics", "schema_migrations",
              "provider_tasks"):
        assert t in tables, f"缺少表 {t}"
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for c in ("goal", "priority", "current_stage", "error_code", "cost_spent", "budget_cap"):
        assert c in cols, f"jobs 缺少列 {c}"
    conn.close()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "idem.db"
    conn = _conn(db)
    migrations.apply_migrations(conn, db_path=db)
    second = migrations.apply_migrations(conn, db_path=db)
    assert second["applied"] == []
    assert migrations.current_version(conn) == migrations.SCHEMA_VERSION
    conn.close()


def test_legacy_db_is_backed_up_and_compat_migrated(tmp_path):
    db = tmp_path / "legacy.db"
    _make_legacy_db(db)

    conn = _conn(db)
    result = migrations.apply_migrations(conn, db_path=db)
    assert result["applied"] == [2, 3, 4]              # v1 基线只补记，不重跑
    assert result["from_version"] == 0
    assert result["backup"], "迁移前必须为老库生成备份"

    # 历史行一条都不能少
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0] == 1

    # 旧状态被一次性映射成 canonical
    mapping = {
        "job_legacy_pending": "PLANNING",
        "job_legacy_trend": "RESEARCHING",
        "job_legacy_generate": "GENERATING",
        "job_legacy_ready": "READY",
        "job_legacy_published": "DONE",
        "job_legacy_failed": "FAILED",
    }
    for uid, expected in mapping.items():
        got = conn.execute("SELECT status FROM jobs WHERE uid=?", (uid,)).fetchone()[0]
        assert got == expected, f"{uid}: {got} != {expected}"

    # 每个被改写的 job 都有 migration event 可追溯
    n_events = conn.execute("SELECT COUNT(*) FROM events WHERE type='migration'").fetchone()[0]
    assert n_events == 6
    conn.close()

    # 备份里保留的是迁移前的老状态（可回滚依据）
    backup = _conn(result["backup"])
    legacy_status = backup.execute(
        "SELECT status FROM jobs WHERE uid='job_legacy_ready'").fetchone()[0]
    assert legacy_status == "ready"
    backup.close()


def test_backup_rotation_keeps_recent(tmp_path):
    db = tmp_path / "rot.db"
    _make_legacy_db(db)
    conn = _conn(db)
    for _ in range(5):
        migrations.backup_db(db, keep=2)
    backups = sorted((tmp_path / "backups").glob("rot_*.db"))
    assert len(backups) == 2
    conn.close()


def test_backup_skipped_for_empty_or_missing_db(tmp_path):
    assert migrations.backup_db(tmp_path / "nope.db") is None
    empty = tmp_path / "empty.db"
    empty.touch()
    assert migrations.backup_db(empty) is None
