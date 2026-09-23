"""轻便侠·AI视频工厂 控制台后端"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from lib import STATE_DIR, OUT_DIR
from lib.state import get_stats, list_jobs, get_job

app = FastAPI(title="轻便侠·AI视频工厂")

# 静态文件和模板
WEBUI_DIR = Path(__file__).parent
THUMBS_DIR = STATE_DIR / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEBUI_DIR / "static"), name="static")
app.mount("/thumbs", StaticFiles(directory=THUMBS_DIR), name="thumbs")
templates = Jinja2Templates(directory=WEBUI_DIR / "templates")

# 运行状态文件
RUN_STATUS_FILE = STATE_DIR / "run_status.json"
RUN_PROGRESS_FILE = STATE_DIR / "run_progress.jsonl"
CONSOLE_STATE_FILE = STATE_DIR / "console.json"

# 6阶段定义
STAGES = [
    {"id": "trend", "name": "热点爆款", "icon": "🔥"},
    {"id": "copy", "name": "文案生成", "icon": "📝"},
    {"id": "storyboard", "name": "智能分镜", "icon": "🎬"},
    {"id": "generate", "name": "视频生成", "icon": "🎥"},
    {"id": "compose", "name": "合成字幕", "icon": "🎞️"},
    {"id": "publish", "name": "发布互动", "icon": "📤"},
]

def load_console_state() -> dict:
    """加载控制台状态"""
    if CONSOLE_STATE_FILE.exists():
        return json.loads(CONSOLE_STATE_FILE.read_text(encoding="utf-8"))
    return {
        "auto_run": False,
        "real_publish": False,
        "real_engage": False,
        "daily_target": 3,
        "last_run": None,
    }

def save_console_state(state: dict):
    """保存控制台状态"""
    CONSOLE_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def load_run_status() -> dict:
    """加载运行状态"""
    if RUN_STATUS_FILE.exists():
        return json.loads(RUN_STATUS_FILE.read_text(encoding="utf-8"))
    return {
        "running": False,
        "current_stage": None,
        "progress": 0,
        "message": "就绪",
        "started_at": None,
    }

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"stages": STAGES},
    )

@app.get("/api/state")
async def api_state():
    """获取控制台状态"""
    return {
        "console": load_console_state(),
        "run": load_run_status(),
        "stats": get_stats(),
        "stages": STAGES,
    }

@app.get("/api/stats")
async def api_stats():
    """获取统计数据"""
    return get_stats()

@app.get("/api/jobs")
async def api_jobs(status: str = None, limit: int = 20):
    """获取任务列表"""
    return list_jobs(status, limit)

@app.get("/api/job/{uid}")
async def api_job(uid: str):
    """获取单个任务"""
    job = get_job(uid)
    if not job:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    return job

@app.post("/api/settings")
async def api_settings(request: Request):
    """更新设置"""
    data = await request.json()
    state = load_console_state()
    state.update(data)
    save_console_state(state)
    return {"ok": True}

@app.post("/api/start")
async def api_start():
    """启动全流程"""
    import subprocess
    
    # 检查是否已在运行
    status = load_run_status()
    if status.get("running"):
        return JSONResponse({"error": "已有任务在运行"}, status_code=400)
    
    # 启动全流程引擎（后台进程）
    engine_script = Path(__file__).parent.parent / "tools" / "run_all.py"
    subprocess.Popen(
        [sys.executable, str(engine_script)],
        cwd=str(Path(__file__).parent.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    
    return {"ok": True, "message": "已启动全流程"}

@app.post("/api/stop")
async def api_stop():
    """停止运行"""
    status = load_run_status()
    status["running"] = False
    status["message"] = "已停止"
    RUN_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}

@app.get("/api/logs")
async def api_logs():
    """SSE 实时日志推送"""
    async def generate() -> AsyncGenerator[str, None]:
        last_pos = 0
        while True:
            # 读取进度文件
            if RUN_PROGRESS_FILE.exists():
                with open(RUN_PROGRESS_FILE, "r", encoding="utf-8") as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    last_pos = f.tell()
                    
                    for line in new_lines:
                        if line.strip():
                            yield f"data: {line.strip()}\n\n"
            
            # 读取运行状态
            status = load_run_status()
            yield f"data: {json.dumps({'type': 'status', 'data': status}, ensure_ascii=False)}\n\n"
            
            await asyncio.sleep(1)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@app.get("/api/outputs")
async def api_outputs(limit: int = 6):
    """获取最新产出（含缩略图）"""
    outputs = []
    if OUT_DIR.exists():
        files = sorted(OUT_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[:limit]:
            thumb = THUMBS_DIR / f"{f.stem}.jpg"
            if not thumb.exists():
                try:
                    import subprocess
                    from lib.tools import ffmpeg
                    subprocess.run(
                        [ffmpeg(), "-y", "-ss", "1", "-i", str(f), "-frames:v", "1",
                         "-vf", "scale=270:480", str(thumb)],
                        capture_output=True, timeout=30)
                except Exception:
                    pass
            outputs.append({
                "name": f.stem,
                "path": str(f),
                "size": f.stat().st_size,
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "thumb": f"/thumbs/{f.stem}.jpg" if thumb.exists() else None,
            })
    return outputs

if __name__ == "__main__":
    print("🏭 轻便侠·AI视频工厂 控制台")
    print("→ http://127.0.0.1:8899")
    uvicorn.run(app, host="127.0.0.1", port=8899, log_level="info")
