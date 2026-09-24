"""轻便侠·AI视频工厂 控制台后端（v2 · Hermes 内核桥接版）

- 流水线状态/日志/产出：原有 API
- Hermes 控制台：/ws/hermes WebSocket 桥接到 hermes serve（tui_gateway JSON-RPC，
  与 Hermes 桌面版本体完全同源：同内核、同模型、同记忆/技能）
- 设置：/api/settings（schema 驱动，前端自动渲染）
- 操作：/api/action/*（登录检测 / 扫码 / 清理 / 打开目录）
"""
import asyncio
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path

# 添加项目根目录 + webui 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from hermes_bridge import blog, get_bridge

from lib import OUT_DIR, STATE_DIR
from lib.state import get_job, get_stats, list_jobs

WEBUI_DIR = Path(__file__).parent
RUN_STATUS_FILE = STATE_DIR / "run_status.json"
RUN_PROGRESS_FILE = STATE_DIR / "run_progress.jsonl"
CONSOLE_STATE_FILE = STATE_DIR / "console.json"
ENGINE_PID_FILE = STATE_DIR / "engine.pid"
_resource_cache: dict = {"at": 0.0, "value": {}}
_cpu_sample: tuple[int, int, int] | None = None


def _windows_cpu_percent() -> float | None:
    """Sample CPU load from GetSystemTimes without requiring psutil."""
    global _cpu_sample
    idle = ctypes.c_ulonglong()
    kernel = ctypes.c_ulonglong()
    user = ctypes.c_ulonglong()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None
    current = (idle.value, kernel.value, user.value)
    previous, _cpu_sample = _cpu_sample, current
    if previous is None:
        return None
    idle_delta = current[0] - previous[0]
    total = current[1] - previous[1] + current[2] - previous[2]
    return round(max(0.0, min(100.0, (1 - idle_delta / total) * 100)), 1) if total > 0 else None


def _windows_memory_percent() -> float | None:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                   ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                   ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                   ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                   ("avail_extended", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    return float(status.load) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None


def resource_stats() -> dict:
    """Real machine telemetry; unavailable sensors remain null on the UI."""
    now = time.monotonic()
    if now - _resource_cache["at"] < 8:
        return _resource_cache["value"]
    disk = shutil.disk_usage(WEBUI_DIR)
    cpu = memory = gpu = None
    try:
        import psutil
        cpu = round(psutil.cpu_percent(interval=None), 1)
        memory = round(psutil.virtual_memory().percent, 1)
    except ImportError:
        if sys.platform == "win32":
            cpu = _windows_cpu_percent()
            memory = _windows_memory_percent()
    except OSError:
        pass
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            result = subprocess.run(
                [exe, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2, check=False)
            readings = [float(x.strip()) for x in result.stdout.splitlines() if x.strip()]
            if readings:
                gpu = round(sum(readings) / len(readings), 1)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass
    value = {"gpu": gpu, "cpu": cpu, "memory": memory,
             "disk": round((1 - disk.free / disk.total) * 100, 1),
             "disk_free_gb": round(disk.free / 1024 ** 3, 1)}
    _resource_cache.update(at=now, value=value)
    return value

# 6阶段定义
STAGES = [
    {"id": "trend", "name": "热点雷达", "icon": "◉", "desc": "捕捉全网热点信号"},
    {"id": "copy", "name": "创意脚本", "icon": "▤", "desc": "策略匹配 + 脚本生成"},
    {"id": "storyboard", "name": "智能分镜", "icon": "◇", "desc": "镜头编排 + 角色选择"},
    {"id": "generate", "name": "视频生成", "icon": "▷", "desc": "多模型并发渲染"},
    {"id": "compose", "name": "合成发布", "icon": "↗", "desc": "装配字幕 + 质量检查"},
    {"id": "publish", "name": "效果追踪", "icon": "⌁", "desc": "多平台发布 + 数据回流"},
]


# ============ 设置 Schema（前端自动渲染，后端白名单校验） ============

PLATFORM_CHOICES = [
    {"id": "douyin", "name": "抖音", "region": "domestic"},
    {"id": "xiaohongshu", "name": "小红书", "region": "domestic"},
    {"id": "shipinhao", "name": "视频号", "region": "domestic"},
    {"id": "tiktok", "name": "TikTok", "region": "overseas"},
    {"id": "instagram", "name": "Instagram", "region": "overseas"},
    {"id": "facebook", "name": "Facebook", "region": "overseas"},
    {"id": "youtube", "name": "YouTube", "region": "overseas"},
    {"id": "telegram", "name": "Telegram", "region": "overseas"},
    {"id": "x", "name": "X (推特)", "region": "overseas"},
]

SETTINGS_SCHEMA = {
    "groups": [
        {
            "id": "pipeline", "name": "生产流水线", "icon": "factory",
            "fields": [
                {"key": "mode", "label": "生产链路", "type": "select",
                 "desc": "模板链路 = 10套爆款模板 + 选角 + 音色克隆（推荐）；旧链路 = 自由脚本分镜",
                 "options": [
                     {"value": "template", "label": "模板链路（推荐）"},
                     {"value": "legacy", "label": "旧链路"},
                 ], "default": "template"},
                {"key": "daily_target", "label": "每日目标产量", "type": "number",
                 "desc": "每次启动全流程生产几条成片", "min": 1, "max": 20, "default": 1},
                {"key": "gen_concurrency", "label": "出片并发数", "type": "number",
                 "desc": "同时生成几个镜头（AutoDL 实测可 10 路，默认 6）",
                 "min": 2, "max": 10, "default": 6},
                {"key": "dry_mode", "label": "演练模式", "type": "toggle",
                 "desc": "开启后全流程走通但不出片、不花钱、不发布", "default": False},
            ],
        },
        {
            "id": "publish", "name": "发布与互动", "icon": "send",
            "fields": [
                {"key": "real_publish", "label": "真发到平台", "type": "toggle", "danger": True,
                 "desc": "关闭 = 只演练不真发；开启 = 成片自动发布到下方勾选的平台", "default": False},
                {"key": "publish_platforms", "label": "发布平台", "type": "multi",
                 "desc": "勾选要发布的平台（开启「真发」后才生效）",
                 "options": PLATFORM_CHOICES, "default": ["douyin"]},
                {"key": "real_engage", "label": "评论/私信维护", "type": "toggle", "danger": True,
                 "desc": "开启后自动回复评论区（关闭时只判定不回复）", "default": False},
            ],
        },
    ]
}

SETTING_KEYS = {f["key"]: f for g in SETTINGS_SCHEMA["groups"] for f in g["fields"]}


def _validate_setting(key: str, value):
    """校验单个设置值，非法返回 (False, reason)"""
    field = SETTING_KEYS.get(key)
    if not field:
        return False, "未知设置项"
    t = field.get("type")
    if t == "toggle":
        return (True, None) if isinstance(value, bool) else (False, "应为开关值")
    if t == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False, "应为数字"
        v = int(value)
        if not (field.get("min", 0) <= v <= field.get("max", 10 ** 9)):
            return False, f"超出范围 {field.get('min')}-{field.get('max')}"
        return True, None
    if t == "select":
        allowed = [o["value"] for o in field.get("options", [])]
        return (True, None) if value in allowed else (False, "非法选项")
    if t == "multi":
        if not isinstance(value, list):
            return False, "应为列表"
        allowed = {o["id"] for o in field.get("options", [])}
        return (True, None) if set(value) <= allowed else (False, "含非法选项")
    return False, "未知类型"


def default_console_state() -> dict:
    return {
        "mode": "template",
        "daily_target": 1,
        "gen_concurrency": 6,
        "dry_mode": False,
        "real_publish": False,
        "real_engage": False,
        "publish_platforms": ["douyin"],
        "last_run": None,
    }


def load_console_state() -> dict:
    state = default_console_state()
    if CONSOLE_STATE_FILE.exists():
        with suppress(Exception):
            state.update(json.loads(CONSOLE_STATE_FILE.read_text(encoding="utf-8")))
    return state


def save_console_state(state: dict):
    CONSOLE_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_run_status() -> dict:
    if RUN_STATUS_FILE.exists():
        try:
            return json.loads(RUN_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"running": False, "current_stage": None, "progress": 0,
            "message": "就绪", "started_at": None}


def engine_alive() -> bool:
    """引擎进程是否真活着（防 run_status 假 running）"""
    if not ENGINE_PID_FILE.exists():
        return False
    try:
        pid = int(ENGINE_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    try:
        import psutil  # 可选依赖
        return psutil.pid_exists(pid)
    except ImportError:
        if sys.platform == "win32":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                               capture_output=True, text=True, errors="replace")
            return str(pid) in (r.stdout or "")
        return True


# ============ Lifespan：预热 Hermes 内核 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    async def warmup():
        try:
            ok, detail = await get_bridge().ensure_ready()
            blog(f"内核预热 {'成功' if ok else '失败'}: {detail}")
        except Exception as e:
            blog(f"内核预热异常: {e}")

    task = asyncio.create_task(warmup())
    yield
    task.cancel()


app = FastAPI(title="轻便侠·AI视频工厂", lifespan=lifespan)
ENGINE_START_LOCK = asyncio.Lock()

THUMBS_DIR = STATE_DIR / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEBUI_DIR / "static"), name="static")
app.mount("/thumbs", StaticFiles(directory=THUMBS_DIR), name="thumbs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=OUT_DIR), name="media")
templates = Jinja2Templates(directory=WEBUI_DIR / "templates")


# ============ 页面 ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"stages": STAGES})


# ============ 流水线 API ============

@app.get("/api/state")
async def api_state():
    status = load_run_status()
    if status.get("running") and not engine_alive():
        # 引擎进程已死但状态没更新（比如被强杀）——纠正为已停止
        status["running"] = False
        status.setdefault("message", "引擎已退出")
    return {
        "console": load_console_state(),
        "run": status,
        "stats": get_stats(),
        "stages": STAGES,
        "hermes": get_bridge().status(),
        "resources": await asyncio.to_thread(resource_stats),
    }


@app.get("/api/stats")
async def api_stats():
    return get_stats()


@app.get("/api/jobs")
async def api_jobs(status: str | None = None, limit: int = Query(default=20, ge=1, le=100)):
    return list_jobs(status, limit)


@app.get("/api/job/{uid}")
async def api_job(uid: str):
    job = get_job(uid)
    if not job:
        return JSONResponse({"error": "任务不存在"}, status_code=404)
    return job


@app.post("/api/settings")
async def api_settings(request: Request):
    """更新设置（schema 白名单校验）"""
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    state = load_console_state()
    saved, ignored = {}, {}
    for key, value in (data or {}).items():
        if key not in SETTING_KEYS:
            ignored[key] = "未知设置项"
            continue
        ok, reason = _validate_setting(key, value)
        if ok:
            state[key] = value
            saved[key] = value
        else:
            ignored[key] = reason
    save_console_state(state)
    return {"ok": True, "saved": saved, "ignored": ignored, "state": state}


@app.get("/api/settings")
async def api_get_settings():
    """当前设置 + schema（前端据此自动渲染设置面板）"""
    state = load_console_state()
    values = {k: state.get(k, SETTING_KEYS[k].get("default")) for k in SETTING_KEYS}
    return {"values": values, "schema": SETTINGS_SCHEMA,
            "platforms": PLATFORM_CHOICES}


@app.post("/api/start")
async def api_start(request: Request):
    """启动全流程"""
    body = {}
    with suppress(Exception):
        body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    stages = body.get("stages")  # 可选：只跑部分阶段
    allowed_stages = {stage["id"] for stage in STAGES}
    if stages is not None and (not isinstance(stages, list) or not stages or any(s not in allowed_stages for s in stages)):
        raise HTTPException(status_code=400, detail="stages 必须是非空、有效的阶段列表")

    async with ENGINE_START_LOCK:
        status = load_run_status()
        if status.get("running") and engine_alive():
            return JSONResponse({"error": "已有任务在运行"}, status_code=400)

        # 面板的演练模式应当真正影响“启动生产”，而非只停留在设置文件里。
        console = load_console_state()
        dry = bool(body["dry"]) if "dry" in body else bool(console.get("dry_mode"))
        engine_script = Path(__file__).parent.parent / "tools" / "run_all.py"
        cmd = [sys.executable, str(engine_script)]
        if stages:
            cmd += ["--only", ",".join(stages)]
        if dry:
            cmd.append("--dry")

        proc = subprocess.Popen(
            cmd, cwd=str(Path(__file__).parent.parent),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        ENGINE_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        # run_all.py 可能要数秒才落状态文件；立即写入避免用户双击时重复拉起。
        RUN_STATUS_FILE.write_text(json.dumps({
            "running": True, "current_stage": None, "progress": 0,
            "message": "生产引擎启动中…", "started_at": datetime.now().isoformat(),
        }, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "message": "已启动全流程" + ("（演练模式）" if dry else ""), "pid": proc.pid}


@app.post("/api/stop")
async def api_stop():
    """停止运行（真停止：kill 引擎进程树）"""
    killed = False
    if ENGINE_PID_FILE.exists():
        try:
            pid = int(ENGINE_PID_FILE.read_text(encoding="utf-8").strip())
            if sys.platform == "win32":
                r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   capture_output=True, timeout=15)
                killed = r.returncode == 0
            else:
                os.kill(pid, 15)
                killed = True
        except (ValueError, ProcessLookupError, subprocess.TimeoutExpired, OSError):
            pass
        ENGINE_PID_FILE.unlink(missing_ok=True)

    status = load_run_status()
    status["running"] = False
    status["message"] = "已停止" if killed else "已停止（引擎进程未找到或已退出）"
    RUN_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "killed": killed}


@app.post("/api/restart")
async def api_restart():
    """安全重启控制台 —— 脱离进程"延时自杀 + 拉起新实例"。

    为什么需要它：面板里的 Hermes 若直接 kill 本进程，会切断自己的
    命令通道（WS 经 webui 转发）导致回合中断（2026-09-24 实测事故）。
    正确姿势 = 调用本端点：命令立即返回，3 秒后由**独立的 bat 进程**
    杀掉旧进程并启动新实例，Hermes 有机会收完输出、体面收尾。

    注意：只杀自己（不用 /T），hermes serve(9277) 保持存活，
    新实例启动后自动复用内核，会话不丢。
    """
    if sys.platform != "win32":
        return JSONResponse({"ok": False, "error": "仅支持 Windows"}, status_code=400)
    pid = os.getpid()
    root = Path(__file__).parent.parent
    bat_path = STATE_DIR / "restart_console.bat"
    content = (
        "@echo off\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        f"taskkill /PID {pid} /F >nul 2>&1\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'cd /d "{root}"\r\n'
        f'start "AYH-MJ Console" "{sys.executable}" webui\\server.py\r\n'
    )
    bat_path.write_text(content, encoding="ascii")
    subprocess.Popen(
        ["cmd", "/c", str(bat_path)], cwd=str(root),
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True)
    return {"ok": True, "message": f"控制台将在 3 秒后重启（旧进程 {pid}）——页面稍后自动重连"}


@app.get("/api/logs")
async def api_logs():
    """SSE 实时日志推送"""
    async def generate() -> AsyncGenerator[str, None]:
        # 新连接只回放末尾，避免运行久后一次性推送巨量历史日志。
        last_pos = max(0, RUN_PROGRESS_FILE.stat().st_size - 12_000) if RUN_PROGRESS_FILE.exists() else 0
        while True:
            if RUN_PROGRESS_FILE.exists():
                try:
                    with open(RUN_PROGRESS_FILE, encoding="utf-8") as f:
                        f.seek(last_pos)
                        new_lines = f.readlines()
                        last_pos = f.tell()
                    for line in new_lines:
                        if line.strip():
                            yield f"data: {line.strip()}\n\n"
                except OSError:
                    pass
            status = load_run_status()
            yield f"data: {json.dumps({'type': 'status', 'data': status}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


def _job_final_label(jobdir: Path) -> str:
    """任务成片的可读名：优先 state/storyboard_<uid>.json 的 模板号+模板名"""
    sb = STATE_DIR / f"storyboard_{jobdir.name.removeprefix('gen_')}.json"
    try:
        data = json.loads(sb.read_text(encoding="utf-8"))
        label = " ".join(str(x) for x in (data.get("template_id"), data.get("template_name")) if x)
        if label.strip():
            return label.strip()
    except Exception:
        pass
    return jobdir.name


def collect_finals() -> list[Path]:
    """只收『最终成片』，按文件时间倒序。

    - out/approved/*.mp4          = 已归档成片（权威）
    - out/gen_job_*/final_sub.mp4 = 未归档的烧字幕成片（缺则退 final.mp4）
    - 排除 shots/shot_*.mp4 等中间镜头
    - 同一部片既在 approved 又在任务目录时，只留 approved（按字节大小去重）
    """
    approved_dir = OUT_DIR / "approved"
    approved = sorted(approved_dir.glob("*.mp4")) if approved_dir.exists() else []
    archived_sizes = {f.stat().st_size for f in approved}

    finals: list[Path] = list(approved)
    for d in sorted(OUT_DIR.glob("gen_job_*")):
        if not d.is_dir():
            continue
        for cand in ("final_sub.mp4", "final.mp4"):  # 带字幕优先
            f = d / cand
            if f.exists():
                if f.stat().st_size not in archived_sizes:  # 已归档 → 不重复展示
                    finals.append(f)
                break
    finals.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return finals


@app.get("/api/outputs")
async def api_outputs(limit: int = Query(default=6, ge=1, le=24)):
    """最新产出（只显示最终成片；缩略图按目录+文件名做唯一键）"""
    outputs = []
    for f in collect_finals()[:limit]:
        try:
            st = f.stat()
        except OSError:
            continue
        safe = re.sub(r"[^\w.\-]", "_", f"{f.parent.name}__{f.stem}")
        thumb = THUMBS_DIR / f"{safe}.jpg"
        if not thumb.exists():
            try:
                from lib.tools import ffmpeg
                subprocess.run(
                    [ffmpeg(), "-y", "-ss", "1", "-i", str(f), "-frames:v", "1",
                     "-vf", "scale=270:480", str(thumb)],
                    capture_output=True, timeout=30)
            except Exception:
                pass
        is_job = f.parent.name.startswith("gen_job_")
        outputs.append({
            "name": _job_final_label(f.parent) if is_job else f.stem,
            "file": f.name,
            "path": str(f),
            "video": f"/media/{f.relative_to(OUT_DIR).as_posix()}",
            "archived": f.parent.name == "approved",
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "thumb": f"/thumbs/{safe}.jpg" if thumb.exists() else None,
        })
    return outputs


# ============ Hermes 内核桥接 ============

@app.websocket("/ws/hermes")
async def ws_hermes(ws: WebSocket):
    """浏览器 WS ←→ hermes serve（原样转发 JSON-RPC）"""
    await get_bridge().proxy(ws)


@app.get("/api/hermes/status")
async def api_hermes_status():
    bridge = get_bridge()
    return {**bridge.status(), "url": f"ws://127.0.0.1:{bridge.port}/api/ws"}


@app.post("/api/hermes/restart")
async def api_hermes_restart():
    ok, detail = await get_bridge().restart()
    return {"ok": ok, "detail": detail}


# ============ 操作类（登录 / 清理 / 目录） ============

ACTION_STATE_FILE = STATE_DIR / "console_action.json"


def _write_action_state(**kw):
    data = {"updated_at": datetime.now().isoformat(), **kw}
    ACTION_STATE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


@app.get("/api/action/state")
async def api_action_state():
    if ACTION_STATE_FILE.exists():
        try:
            return json.loads(ACTION_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@app.post("/api/action/douyin_check")
async def api_douyin_check():
    """检测抖音登录态（后台跑 browser.py --check，前端轮询 /api/action/state）"""
    async def run_check():
        _write_action_state(kind="douyin_check", status="running", message="检测中…")
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(Path(__file__).parent.parent / "s1_trend" / "browser.py"), "--check",
                cwd=str(Path(__file__).parent.parent),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=150)
            text = (out or b"").decode("utf-8", errors="replace")
            ok = "✓" in text and "未登录" not in text
            _write_action_state(kind="douyin_check",
                                status="ok" if ok else "fail",
                                message=text.strip()[-300:] or ("登录有效 ✓" if ok else "未登录"))
        except TimeoutError:
            _write_action_state(kind="douyin_check", status="fail", message="检测超时")
        except Exception as e:
            _write_action_state(kind="douyin_check", status="fail", message=f"检测异常: {e}")

    asyncio.create_task(run_check())
    return {"ok": True, "message": "检测已启动"}


@app.post("/api/action/douyin_login")
async def api_douyin_login():
    """弹出扫码登录窗口（后台跑 browser.py --login）"""
    subprocess.Popen(
        [sys.executable, str(Path(__file__).parent.parent / "s1_trend" / "browser.py"), "--login"],
        cwd=str(Path(__file__).parent.parent),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    return {"ok": True, "message": "扫码窗口即将弹出，请在窗口中完成扫码"}


@app.post("/api/action/cleanup")
async def api_cleanup(request: Request):
    """清理项目（默认 dry-run 预览；body {confirm: true} 才真删）"""
    body = {}
    with suppress(Exception):
        body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    confirm = bool(body.get("confirm"))
    cmd = [sys.executable, str(Path(__file__).parent.parent / "tools" / "cleanup_project.py")]
    if not confirm:
        cmd.append("--dry")
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(Path(__file__).parent.parent),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise HTTPException(status_code=504, detail="清理任务超时，已终止") from exc
    text = (out or b"").decode("utf-8", errors="replace")
    return {"ok": True, "confirm": confirm, "output": text.strip()[-3000:]}


@app.post("/api/action/open_output")
async def api_open_output():
    """打开输出目录"""
    if sys.platform == "win32":
        os.startfile(str(OUT_DIR))  # noqa: S606
    return {"ok": True, "path": str(OUT_DIR)}


# ============ 兼容：旧版 chat 端点（新前端不用，保留供排查） ============

CHAT_STATE_FILE = STATE_DIR / "chat_session.json"
CHAT_LOG_DIR = STATE_DIR / "logs"
CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)
CHAT_HISTORY_FILE = STATE_DIR / "chat.json"
CHAT_LOG_FILE = CHAT_LOG_DIR / "chat_current.log"


def _load_chat_session() -> dict:
    if CHAT_STATE_FILE.exists():
        try:
            return json.loads(CHAT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"session_id": None}


@app.get("/api/chat/history")
async def api_chat_history():
    if CHAT_HISTORY_FILE.exists():
        try:
            return json.loads(CHAT_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


if __name__ == "__main__":
    print("🏭 轻便侠·AI视频工厂 控制台 v2")
    print("→ http://127.0.0.1:8899")
    # reload 模式（默认）：webui/ 下 Python 代码保存后自动重载 ——
    # 面板里的 Hermes 改完 server.py / hermes_bridge.py 无需重启即可生效，
    # 且 worker 意外退出时由 reloader 主进程自动复活。
    # 设 AYH_NO_RELOAD=1 可关闭（调试 reload 本身时用）。
    if os.environ.get("AYH_NO_RELOAD") == "1":
        uvicorn.run(app, host="127.0.0.1", port=8899, log_level="info")
    else:
        uvicorn.run(
            "webui.server:app", host="127.0.0.1", port=8899, log_level="info",
            reload=True, reload_dirs=[str(WEBUI_DIR)],
        )
