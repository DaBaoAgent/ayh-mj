"""Phase 12：WebUI 任务控制台 Playwright 验收（启动 / 取消 / 失败修复 / READY / 发布阻断）。

隔离原则与 Phase 0 smoke 一致：uvicorn 起在空闲端口上，state 与 out 都指向临时目录，
造数由**独立子进程**写同一份 canonical 事实源（JobStore）。全程演练模式，不联网、不付费。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.frontend

playwright_api = pytest.importorskip("playwright.sync_api",
                                     reason="playwright 未安装，跳过前端验收")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return r.status, json.loads(r.read().decode("utf-8"))


def _post(url: str, payload: dict | None = None, timeout: float = 30.0):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:                      # 4xx 也要能读到 body
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture(scope="module")
def webui(tmp_path_factory):
    root = tmp_path_factory.mktemp("webui12")
    state_dir, out_dir = root / "state", root / "out"
    state_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
           "AYHMJ_STATE_DIR": str(state_dir), "AYHMJ_OUT_DIR": str(out_dir)}
    port = _free_port()
    # 必须重定向到文件而不是 PIPE：没人读的 PIPE 写满缓冲区后会把 uvicorn 整个进程
    # 阻塞在写 stdout 上，表现为「前几个用例过后所有请求无响应」（实测 30s goto 超时）。
    log_path = root / "uvicorn.log"
    log_fh = open(log_path, "wb")  # noqa: SIM115 - 生命周期跨 yield，由 finally 关闭
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webui.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--lifespan", "off",
         "--log-level", "warning"],
        cwd=str(ROOT), stdout=log_fh, stderr=subprocess.STDOUT, env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            if proc.poll() is not None:
                log_fh.flush()
                out = log_path.read_text(encoding="utf-8", errors="replace")
                pytest.fail(f"uvicorn 提前退出:\n{out[-1500:]}")
            try:
                if _get(f"{base}/api/state", timeout=1.5)[0] == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            pytest.fail("uvicorn 未在 30s 内就绪")
        yield {"base": base, "state": state_dir, "out": out_dir, "env": env}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as pw:
        instance = pw.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture()
def page(browser, webui):
    # 每个用例一个独立 BrowserContext：browser.new_page() 隐式建的 context 从不回收，
    # 页面里 EventSource(SSE) 长连接会随 context 一起堆积，把后续导航拖到 30s 超时。
    context = browser.new_context()
    page = context.new_page()
    errors: list[str] = []
    page.set_default_timeout(20000)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())          # 取消/重试有 window.confirm
    yield page
    page.close()
    context.close()
    assert not errors, f"页面 JS 报错: {errors}"


def seed(webui, jobs: list[dict]) -> list[str]:
    """在独立子进程里按 spec 造数（与服务端共享同一个 state 目录）。"""
    spec_path = webui["state"].parent / f"seed_{int(time.time() * 1000)}.json"
    spec_path.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, "tests/p12_seed.py", str(spec_path)],
                          cwd=str(ROOT), env=webui["env"], capture_output=True, timeout=120)
    if proc.returncode != 0:
        pytest.fail(f"造数失败: {proc.stderr.decode('utf-8', 'replace')[-1200:]}")
    return json.loads(proc.stdout.decode("utf-8"))["uids"]


def job_of(webui, uid: str) -> dict:
    status, body = _get(f"{webui['base']}/api/jobs/{uid}")
    assert status == 200, body
    return body


def wait_status(webui, uid: str, status: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = job_of(webui, uid)
        if last["job"]["status"] == status:
            return last
        time.sleep(0.4)
    pytest.fail(f"{uid} 未在 {timeout}s 内到达 {status}（当前 {last.get('job', {}).get('status')}）")


def open_console(page, webui, uid: str):
    page.goto(webui["base"], wait_until="domcontentloaded")
    row = page.locator(f'button.job-row[data-uid="{uid}"]')
    row.wait_for(state="visible", timeout=20000)
    row.click()
    page.locator("#jobDrawer.open").wait_for(state="visible", timeout=10000)
    # 抽屉是异步渲染的：等详情真正画出来再断言，避免读到"加载任务详情…"
    page.locator("#jobDrawerBody .job-section").first.wait_for(state="visible", timeout=15000)


# ── 1. 启动（真实 UI 按钮）+ 刷新后任务仍在 ─────────────────────────────

def test_start_button_creates_real_job_and_survives_refresh(page, webui):
    status, _ = _post(f"{webui['base']}/api/settings", {"dry_mode": True})
    assert status == 200
    before = {j["uid"] for j in _get(f"{webui['base']}/api/jobs")[1]["jobs"]}

    page.goto(webui["base"], wait_until="domcontentloaded")
    page.locator("#btnStart").click()

    deadline, uid = time.time() + 30, None
    while time.time() < deadline and uid is None:
        for job in _get(f"{webui['base']}/api/jobs")[1]["jobs"]:
            if job["uid"] not in before:
                uid = job["uid"]
                break
        time.sleep(0.5)
    assert uid, "点击启动后没有产生新任务"
    wait_status(webui, uid, "READY")

    # 页面刷新后：任务事实与 canonical 状态都还在（不靠前端内存）
    page.reload(wait_until="domcontentloaded")
    page.locator(f'button.job-row[data-uid="{uid}"]').wait_for(state="visible", timeout=20000)
    assert page.locator(f'button.job-row[data-uid="{uid}"]').get_attribute("data-status") == "READY"
    strip = page.inner_text("#stateStrip")
    assert "待发布" in strip or "已完成" in strip
    assert "失败" not in page.inner_text("#statusText")


# ── 1b. 刷新恢复：运行中的任务按 canonical 事实恢复，不靠前端内存 ────────

def test_running_job_survives_refresh_with_canonical_state(page, webui):
    """验收 1：刷新页面后，运行中的任务必须按 JobStore 的事实恢复显示。"""
    seed(webui, [
        {"uid": "job_p12_running", "goal": "运行中用例", "status": "GENERATING",
         "cost_spent": 0.4, "attempts": [{"stage": "generate", "status": "RUNNING"}]},
        {"uid": "job_p12_paused", "goal": "重启收敛用例", "status": "PAUSED",
         "error_code": "ENGINE_RESTART", "error_stage": "generate"},
    ])
    page.goto(webui["base"], wait_until="domcontentloaded")
    running = page.locator('button.job-row[data-uid="job_p12_running"]')
    running.wait_for(state="visible", timeout=20000)
    assert running.get_attribute("data-status") == "GENERATING"
    assert "视频生成" in running.inner_text()

    # 刷新：状态只能重新从服务端事实源读回来（前端没有任何内存可依赖）
    page.reload(wait_until="domcontentloaded")
    running = page.locator('button.job-row[data-uid="job_p12_running"]')
    running.wait_for(state="visible", timeout=20000)
    assert running.get_attribute("data-status") == "GENERATING"
    assert "视频生成" in running.inner_text()
    # 旁路态（重启后收敛为 PAUSED）同样必须被如实展示
    assert page.locator('button.job-row[data-uid="job_p12_paused"]') \
        .get_attribute("data-status") == "PAUSED"


# ── 2. 取消：UI 点击后 DB 状态一致 ──────────────────────────────────────

def test_cancel_from_drawer_matches_db(page, webui):
    uid = seed(webui, [{"uid": "job_p12_cancel", "goal": "取消用例", "status": "READY",
                        "artifacts": [{"type": "final", "name": "cancel.mp4"}]}])[0]
    open_console(page, webui, uid)
    assert "待发布" in page.inner_text("#jobDrawerTitle")
    page.locator('#jobDrawer button[data-action="cancel"]').click()
    wait_status(webui, uid, "CANCELLED")
    page.wait_for_selector(f'button.job-row[data-uid="{uid}"][data-status="CANCELLED"]',
                           timeout=20000)
    # 动作成功后抽屉会重新拉一次详情（其间显示"加载任务详情…"），必须等它落定再断言。
    page.wait_for_function(
        "() => /取消/.test((document.querySelector('#jobDrawerTitle') || {}).textContent || '')",
        timeout=20000)
    assert "取消" in page.inner_text("#jobDrawerTitle") or "已取消" in page.inner_text("#jobDrawerBody")


# ── 3. 失败 → 需要人工 → 重试修复到 READY ───────────────────────────────

def test_failed_job_explains_human_and_retry_recovers(page, webui):
    uid = seed(webui, [{"uid": "job_p12_failed", "goal": "失败修复用例", "status": "FAILED",
                        "error_code": "VISUAL_QA_FAIL", "error_stage": "qa",
                        "repairs": [{"error_code": "VISUAL_QA_FAIL", "cost": 0.2}],
                        "attempts": [{"stage": "qa", "status": "FAILED",
                                      "error_code": "VISUAL_QA_FAIL"}]}])[0]
    open_console(page, webui, uid)
    drawer = page.inner_text("#jobDrawer")
    assert "需要人工" in drawer and "VISUAL_QA_FAIL" in drawer
    assert "重出" in drawer                       # 人话提示，而不是只丢错误码
    assert "修复次数" in drawer and "1" in drawer

    page.locator('#jobDrawer button[data-action="retry"]').click()
    wait_status(webui, uid, "READY")
    assert job_of(webui, uid)["job"]["error_code"] is None
    # UI 刷新后也必须显示 canonical 的 READY（不是旧一行缓存）
    page.wait_for_selector(f'button.job-row[data-uid="{uid}"][data-status="READY"]', timeout=25000)


# ── 4. READY：成片区展示视频 / QA / 标题封面 / 发布 / 表现 ───────────────

def test_ready_material_card_shows_production_facts(page, webui):
    uid = seed(webui, [{
        "uid": "job_p12_ready", "goal": "成片物料用例", "status": "READY", "cost_spent": 2.5,
        "creative": {"structure": "S_duo_conflict", "genre": "G1"},
        "artifacts": [{"type": "final", "name": "ready_case.mp4",
                       "content": "final-video-bytes", "stage": "package"}],
        "qa": [{"kind": "qa_critic", "score": 0.91, "passed": True}],
        "attempts": [{"stage": "generate", "status": "SUCCESS", "cost": 1.2}],
        "publishes": [{"platform": "douyin", "status": "DRAFT"}],
        "performance": [{"platform": "douyin", "views": 1200, "completion": 0.42, "likes": 31}],
    }])[0]
    seed_packaging(webui, uid, {"chosen_title": "标题：单手拎起", "cover_text": "封面：真轻",
                                "hashtags": ["#轻便", "#出行"]})

    page.goto(webui["base"], wait_until="domcontentloaded")
    card = page.locator(f'#materialsList .material-card[data-uid="{uid}"]')
    card.wait_for(state="visible", timeout=20000)
    text = card.inner_text()
    assert "ready_case.mp4" in text
    assert "标题：单手拎起" in text and "封面：真轻" in text
    assert "QA" in text and "0.91" in text
    assert "douyin/DRAFT" in text
    assert "表现" in text and "3 个指标" in text and "完播 42.0%" in text
    assert card.locator('a.material-link[href="/media/ready_case.mp4"]').count() == 1

    open_console(page, webui, uid)
    drawer = page.inner_text("#jobDrawer")
    assert "CREATIVEDNA" in drawer.upper(), drawer
    assert "G1" in drawer, drawer
    assert "产物" in drawer and "ready_case.mp4" in drawer
    assert "质检与评分" in drawer


def seed_packaging(webui, uid: str, payload: dict) -> None:
    """补一份 packaging artifact（走造数子进程，保证 DB 与文件一致）。"""
    path = webui["state"] / f"packaging_{uid}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    code = (
        f"import sys, json; sys.path.insert(0, r'{ROOT}');\n"
        f"from lib.jobstore import store\n"
        f"print(store.add_artifact('{uid}', 'packaging', r'{path}'))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=webui["env"],
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-800:]


# ── 5. 发布阻断：BLOCKED 必须说明为什么需要人工 ─────────────────────────

def test_publish_blocked_job_tells_user_why(page, webui):
    uid = seed(webui, [{
        "uid": "job_p12_blocked", "goal": "发布阻断用例", "status": "BLOCKED",
        "error_code": "AI_DISCLOSURE_UNCONFIRMED", "error_stage": "publishing",
        "artifacts": [{"type": "final", "name": "blocked_case.mp4"}],
    }])[0]
    open_console(page, webui, uid)
    drawer = page.inner_text("#jobDrawer")
    assert "需要人工" in drawer
    assert "AI_DISCLOSURE_UNCONFIRMED" in drawer
    assert "草稿" in drawer or "人工发布" in drawer       # 后端给的人话提示
    assert "系统建议动作" in drawer

    page.goto(webui["base"], wait_until="domcontentloaded")
    card = page.locator(f'#materialsList .material-card[data-uid="{uid}"]')
    card.wait_for(state="visible", timeout=20000)
    assert "需人工" in card.inner_text()
    assert card.get_attribute("data-status") == "BLOCKED"
