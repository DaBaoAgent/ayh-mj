"""Hermes 内核桥接 —— webui 内嵌与桌面版同源的 Hermes。

架构
    浏览器 ──WS  ws://127.0.0.1:8899/ws/hermes ──> webui (FastAPI)
           ──WS  ws://127.0.0.1:9277/api/ws?token=… ──> hermes serve

hermes serve 跑的是 tui_gateway 的 JSON-RPC 协议 —— 与 Hermes 桌面版
聊天通道完全同一个实现（同一 agent 内核、同一份配置/记忆/技能/模型）。
本模块只做两件事：
  1. serve 子进程生命周期（探测 → 复用 或 拉起；专用端口 + 持久化 token）
  2. WebSocket 双向原样转发（浏览器 ←→ serve）

事件流（前端渲染依据，与桌面版语义一致）：
    gateway.ready        连接就绪（含 skin 主题）
    message.start        回合开始
    thinking.delta       等待提示文案（kawaii spinner，进状态行）
    reasoning.delta      思考过程（逐 token 流，"思考"折叠块）
    reasoning.available  思考过程（整块文本）
    message.delta        回复文本（逐 token 流）
    message.interim      回合中插话（独立小气泡）
    message.complete     回合结束（含 usage / error）
    tool.generating / tool.start / tool.progress / tool.complete   工具调用
    session.title / session.info / sessions.changed               会话元信息
    approval.request / clarify.request / sudo.request             交互请求
    status.update / error / reaction / todo.updated               其他
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

try:  # websockets ≥ 13 的新式 asyncio 客户端
    from websockets.asyncio.client import connect as ws_connect
except ImportError:  # pragma: no cover - 兼容旧版
    from websockets.client import connect as ws_connect  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
LOG_DIR = STATE_DIR / "logs"
BRIDGE_STATE_FILE = STATE_DIR / "hermes_bridge.json"
SERVE_LOG_FILE = LOG_DIR / "hermes_serve.log"
BRIDGE_LOG_FILE = LOG_DIR / "bridge.log"

# 专用端口：避开桌面版 Hermes 默认的 9119，防止互相抢 attach
DEFAULT_PORT = 9277
FALLBACK_PORTS = [9317, 9357, 9397]

MAX_FRAME = 32 * 1024 * 1024  # 单条事件最大 32MB（工具结果可能较大）
TOKEN_PREFIX = "ayhmj-"


def blog(msg: str) -> None:
    """bridge 日志（控制台 + state/logs/bridge.log）"""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(f"[bridge] {msg}", flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(BRIDGE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class HermesBridge:
    """hermes serve 生命周期 + WebSocket 转发。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._ready = False
        self._last_error = ""
        self.pid: int | None = None
        self._load_state()

    # ── 状态持久化 ──────────────────────────────────────────────

    def _load_state(self) -> None:
        data = {}
        if BRIDGE_STATE_FILE.exists():
            try:
                data = json.loads(BRIDGE_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        self.token = str(data.get("token") or (TOKEN_PREFIX + secrets.token_urlsafe(24)))
        try:
            self.port = int(data.get("port") or DEFAULT_PORT)
        except (TypeError, ValueError):
            self.port = DEFAULT_PORT
        self.pid = data.get("pid")
        self._save_state()

    def _save_state(self) -> None:
        try:
            BRIDGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            BRIDGE_STATE_FILE.write_text(
                json.dumps(
                    {"token": self.token, "port": self.port, "pid": self.pid,
                     "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                    ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass

    # ── 探测 / 启动 ─────────────────────────────────────────────

    def _ws_url(self, port: int) -> str:
        return f"ws://127.0.0.1:{port}/api/ws?token={self.token}"

    async def _probe_ws(self, port: int, timeout: float = 8.0) -> bool:
        """WS 连上去：收到 gateway.ready 即认为实例可用（token 也对）"""
        try:
            async with ws_connect(self._ws_url(port), max_size=1 << 20,
                                  proxy=None, open_timeout=timeout,
                                  close_timeout=2) as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                return '"gateway.ready"' in raw
        except Exception:
            return False

    def _spawn(self, port: int) -> subprocess.Popen:
        exe = shutil.which("hermes") or "hermes"
        env = os.environ.copy()
        # 清理 venv 污染（SRE module mismatch 坑）
        for k in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
            env.pop(k, None)
        env["HERMES_DASHBOARD_SESSION_TOKEN"] = self.token
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        blog(f"启动 hermes serve :{port} (exe={exe})")
        with open(SERVE_LOG_FILE, "a", encoding="utf-8") as log_fh:
            log_fh.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} serve :{port} =====\n")
            proc = subprocess.Popen(
                [exe, "serve", "--skip-build", "--port", str(port)],
                cwd=str(ROOT), stdout=log_fh, stderr=subprocess.STDOUT,
                env=env, creationflags=flags)
        return proc

    async def ensure_ready(self, wait_timeout: float = 120.0) -> tuple[bool, str]:
        """确保 serve 可用。能连就复用；不能连就拉起。返回 (ok, 说明)"""
        async with self._lock:
            if await self._probe_ws(self.port):
                self._ready = True
                self._last_error = ""
                return True, f"复用实例 127.0.0.1:{self.port}"

            ports = [self.port] + [p for p in FALLBACK_PORTS if p != self.port]
            for port in ports:
                if _port_in_use(port):
                    continue
                proc = self._spawn(port)
                self.pid = proc.pid
                self.port = port
                self._save_state()
                deadline = time.monotonic() + wait_timeout
                while time.monotonic() < deadline:
                    await asyncio.sleep(2.5)
                    if proc.poll() is not None:
                        msg = (f"serve 进程退出（code={proc.returncode}），"
                               f"日志：state/logs/{SERVE_LOG_FILE.name}")
                        self._last_error = msg
                        blog(msg)
                        return False, msg
                    if await self._probe_ws(port, timeout=5):
                        self._ready = True
                        self._last_error = ""
                        blog(f"serve 就绪 :{port} (pid={proc.pid})")
                        return True, f"已启动新实例 127.0.0.1:{port} (pid={proc.pid})"
                msg = f"serve 启动超时（{wait_timeout:.0f}s），日志：state/logs/{SERVE_LOG_FILE.name}"
                self._last_error = msg
                blog(msg)
                return False, msg
            msg = "无可用端口（" + ", ".join(str(p) for p in ports) + " 均被占用）"
            self._last_error = msg
            return False, msg

    async def restart(self) -> tuple[bool, str]:
        """重启 serve（杀掉现有实例再拉起）"""
        async with self._lock:
            if self.pid:
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/PID", str(self.pid), "/T", "/F"],
                                       capture_output=True, timeout=15)
                    else:
                        os.kill(int(self.pid), 15)
                except Exception as e:
                    blog(f"restart: 杀进程失败 {e}")
            self._ready = False
            self.pid = None
            self._save_state()
        # 等待端口释放
        for _ in range(20):
            if not _port_in_use(self.port):
                break
            await asyncio.sleep(0.5)
        return await self.ensure_ready()

    # ── WS 转发 ─────────────────────────────────────────────────

    async def proxy(self, client) -> None:
        """把一条浏览器 WS 原样桥接到 hermes serve（双向）。"""
        await client.accept()
        ok, detail = await self.ensure_ready()
        if not ok:
            try:
                await client.send_text(json.dumps({
                    "jsonrpc": "2.0", "method": "event",
                    "params": {"type": "bridge.error", "payload": {"message": detail}},
                }, ensure_ascii=False))
            except Exception:
                pass
            try:
                await client.close(code=4503)
            except Exception:
                pass
            return

        try:
            upstream = await ws_connect(
                self._ws_url(self.port), max_size=MAX_FRAME, proxy=None,
                open_timeout=15, ping_interval=20, ping_timeout=20,
                close_timeout=3)
        except Exception as e:
            blog(f"连 serve 失败: {e}")
            try:
                await client.close(code=4503)
            except Exception:
                pass
            self._ready = False
            return

        async def c2u() -> None:
            while True:
                text = await client.receive_text()
                await upstream.send(text)

        async def u2c() -> None:
            async for raw in upstream:
                await client.send_text(raw)

        t1 = asyncio.create_task(c2u())
        t2 = asyncio.create_task(u2c())
        try:
            await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (t1, t2):
                t.cancel()
            await asyncio.gather(t1, t2, return_exceptions=True)
            try:
                await upstream.close()
            except Exception:
                pass

    # ── 状态 ────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "ready": self._ready,
            "port": self.port,
            "pid": self.pid,
            "error": self._last_error,
        }


_bridge: HermesBridge | None = None


def get_bridge() -> HermesBridge:
    global _bridge
    if _bridge is None:
        _bridge = HermesBridge()
    return _bridge
