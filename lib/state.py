"""SQLite 状态管理"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import STATE_DIR

DB_PATH = STATE_DIR / "pipeline.db"

# 任务状态
JOB_STATUS = {
    "pending": "待处理",
    "trend": "抓热点中",
    "copy": "生成文案中",
    "storyboard": "分镜中",
    "generate": "生成视频中",
    "compose": "合成中",
    "ready": "待发布",
    "published": "已发布",
    "failed": "失败",
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
    """上下文管理器"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """初始化数据库表"""
    with connect() as conn:
        conn.executescript("""
            -- 热点素材
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
                keywords TEXT,  -- JSON array
                score REAL,
                matched INTEGER DEFAULT 0,  -- 是否匹配产品
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- 生产任务
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT NOT NULL UNIQUE,  -- 任务唯一ID
                trend_id INTEGER REFERENCES trends(id),
                status TEXT DEFAULT 'pending',

                -- 文案
                script TEXT,
                script_word_count INTEGER,

                -- 分镜
                storyboard TEXT,  -- JSON array

                -- 视频
                shots TEXT,  -- JSON array, 每个镜头的视频路径

                -- 合成
                video_path TEXT,
                duration REAL,

                -- 封面
                covers TEXT,  -- JSON object {3:4, 4:3, 16:9}

                -- 发布
                publish_results TEXT,  -- JSON object

                -- 时间
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                published_at TEXT
            );

            -- 发布记录
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

            -- 互动记录
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                post_id TEXT NOT NULL,
                comment_id TEXT NOT NULL UNIQUE,
                comment_text TEXT,
                commenter TEXT,
                reply_text TEXT,
                reply_status TEXT DEFAULT 'pending',  -- pending/replied/escalated/spam
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                replied_at TEXT
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_trends_platform ON trends(platform);
            CREATE INDEX IF NOT EXISTS idx_trends_score ON trends(score DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_uid ON jobs(uid);
        """)
        conn.commit()

def create_job(trend_id: int = None) -> str:
    """创建新任务，返回uid（微秒级时间戳防同秒碰撞）"""
    uid = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{trend_id or 0}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO jobs (uid, trend_id, status) VALUES (?, ?, 'pending')",
            (uid, trend_id)
        )
        conn.commit()
    return uid


_FIELD_WHITELIST = {
    "trend_id", "status", "script", "script_word_count", "storyboard", "shots",
    "video_path", "duration", "covers", "publish_results", "published_at",
}


def update_job(uid: str, **kwargs):
    """更新任务（字段白名单校验，防注入与错字）"""
    bad = set(kwargs) - _FIELD_WHITELIST
    if bad:
        raise ValueError(f"update_job 不允许的字段: {bad}（白名单: {sorted(_FIELD_WHITELIST)}）")
    kwargs["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {sets} WHERE uid = ?", [*kwargs.values(), uid])
        conn.commit()

def get_job(uid: str) -> dict:
    """获取任务"""
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None

def list_jobs(status: str = None, limit: int = 20) -> list:
    """列出任务"""
    with connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

def get_stats() -> dict:
    """获取统计数据"""
    with connect() as conn:
        today = datetime.now().strftime("%Y-%m-%d")
        stats = {
            "trends_total": conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0],
            "trends_today": conn.execute(
                "SELECT COUNT(*) FROM trends WHERE created_at >= ?", (today,)
            ).fetchone()[0],
            "jobs_total": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "jobs_pending": conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'pending'"
            ).fetchone()[0],
            "jobs_ready": conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'ready'"
            ).fetchone()[0],
            "jobs_published": conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'published'"
            ).fetchone()[0],
            "published_today": conn.execute(
                "SELECT COUNT(*) FROM publishes WHERE created_at >= ?", (today,)
            ).fetchone()[0],
        }
        return stats

# 初始化
init_db()
