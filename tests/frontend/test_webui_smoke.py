"""WebUI 最小 Playwright smoke（Phase 0）。

覆盖：页面能打开、settings 能加载、Start/Stop API 能响应、Hermes WS 不可用时 UI 不崩。
不联网、不付费：`uvicorn` 以 `--lifespan off` 启动，避免预热 Hermes 内核。
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.frontend

playwright_api = pytest.importorskip("playwright.sync_api",
                                     reason="playwright 未安装，跳过前端 smoke")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8"))


def _post(url: str, payload: dict | None = None, timeout: float = 20.0):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8"))


@pytest.fixture(scope="module")
def webui_server():
    port = _free_port()
    env = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webui.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--lifespan", "off",
         "--log-level", "warning"],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**__import__("os").environ, **env})
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            if proc.poll() is not None:
                out = (proc.stdout.read() or b"").decode("utf-8", "replace")
                pytest.fail(f"uvicorn 提前退出:\n{out[-1500:]}")
            try:
                status, _ = _get(f"{base}/api/state", timeout=1.5)
                if status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            pytest.fail("uvicorn 未在 30s 内就绪")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_page_renders_and_settings_load(webui_server):
    status, payload = _get(f"{webui_server}/api/settings")
    assert status == 200
    assert set(payload) >= {"values", "schema", "platforms"}
    assert "daily_target" in payload["schema"]["groups"][0]["fields"][0]["key"]

    with playwright_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(webui_server, wait_until="networkidle", timeout=20000)
        assert page.title()
        # 核心容器存在
        assert page.locator("body").count() == 1
        browser.close()
        assert not errors, f"页面 JS 报错: {errors}"


def test_start_and_stop_api_respond(webui_server):
    status, body = _post(f"{webui_server}/api/start", {"dry": True})
    assert status == 200 and body.get("ok"), body
    time.sleep(0.5)
    status, body = _post(f"{webui_server}/api/stop")
    assert status == 200 and body.get("ok"), body


def test_hermes_ws_unavailable_does_not_break_api(webui_server):
    # Hermes 内核此处必然不可用（未预热）；页面/接口仍须正常响应。
    status, payload = _get(f"{webui_server}/api/hermes/status")
    assert status == 200
    assert "ready" in payload
    status, state = _get(f"{webui_server}/api/state")
    assert status == 200
    assert "hermes" in state
