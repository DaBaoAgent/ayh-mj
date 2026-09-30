"""SQLite 连接 + 兼容门面（Phase 2 起事实源是 `lib.jobstore`）。

本模块只负责：
  · 数据库连接与 schema migration（`lib.migrations`）；
  · trends / publishes / interactions 等既有表的读写；
  · 旧 job API（create_job / update_job / get_job / list_jobs / get_stats）的兼容门面，
    全部委托给 `lib.jobstore.JobStore`，状态转换走状态机校验。

新代码请直接用 `lib.jobstore.store`，不要在这里写裸 SQL 改状态。
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import STATE_DIR, migrations

DB_PATH = STATE_DIR / "pipeline.db"

# 旧状态 → 展示名（保留以兼容 WebUI/老脚本的 import）
JOB_STATUS = {
    "PENDING": "待处理",
    "PLANNING": "规划中",
    "RESEARCHING": "调研中",
    "SCRIPTING": "写作中",
    "PREFLIGHT": "预检中",
    "GENERATING": "生成视频中",
    "QA": "验片中",
    "REPAIRING": "修复中",
    "COMPOSING": "合成中",
    "PACKAGING": "包装中",
    "READY": "待发布",
    "PUBLISHING": "发布中",
    "LEARNING": "学习中",
    "DONE": "已完成",
    "PAUSED": "已暂停",
    "BLOCKED": "受阻",
    "FAILED": "失败",
    "CANCELLED": "已取消",
}

def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def connect():
    """上下文管理器（退出时自动提交；异常回滚）"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """初始化/迁移数据库（幂等；迁移前自动备份非空旧库）。"""
    with connect() as conn:
        result = migrations.apply_migrations(conn, db_path=DB_PATH)
        conn.commit()
    return result

def create_job(trend_id: int = None) -> str:
    """创建新任务（兼容门面，委托 JobStore）。"""
    from .jobstore import store
    return store.create_job(trend_id=trend_id)


def update_job(uid: str, **kwargs):
    """更新任务（兼容门面）。

    `status` 走状态机校验；其余字段走白名单。非法状态转换会抛
    `lib.jobstore.InvalidTransition`，绝不静默改库。
    """
    from .jobstore import store
    status = kwargs.pop("status", None)
    if status is not None:
        store.transition(uid, status, message="update_job() 兼容调用")
    if kwargs:
        store.set_fields(uid, **kwargs)

def get_job(uid: str) -> dict:
    """获取任务"""
    from .jobstore import store
    return store.get_job(uid)

def list_jobs(status: str = None, limit: int = 20) -> list:
    """列出任务"""
    from .jobstore import store
    return store.list_jobs(status, limit)

def get_stats() -> dict:
    """获取统计数据"""
    from .jobstore import JobState, store
    with connect() as conn:
        today = datetime.now().strftime("%Y-%m-%d")
        counts = store.counts()
        by_status = counts["by_status"]
        pending = sum(v for k, v in by_status.items()
                      if k not in (JobState.READY, JobState.DONE, JobState.CANCELLED,
                                   JobState.FAILED))
        stats = {
            "trends_total": conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0],
            "trends_today": conn.execute(
                "SELECT COUNT(*) FROM trends WHERE created_at >= ?", (today,)
            ).fetchone()[0],
            "jobs_total": counts["total"],
            "jobs_pending": pending,
            "jobs_ready": by_status.get(JobState.READY, 0),
            "jobs_published": by_status.get(JobState.DONE, 0),
            "jobs_by_status": by_status,
            "published_today": conn.execute(
                "SELECT COUNT(*) FROM publishes WHERE created_at >= ?", (today,)
            ).fetchone()[0],
        }
        return stats

# 初始化
init_db()
