"""抖音浏览器上下文（有头 + 窗口移到屏幕外）

已知坑（来自 AutoAYH 实战）：
  · headless 会被识别（搜索页返验证页）→ 必须 headless=False + --window-position=-3000,-3000
  · 登录态判定必须用接口（cookie 里 sessionid ≠ 登录有效）
  · playwright 与 patchright 共用 %LOCALAPPDATA%\\ms-playwright，缺 chromium 时退回 Edge
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import STATE_DIR

PROFILE_DIR = STATE_DIR / "browser-profile"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled",
               "--window-position=-3000,-3000", "--mute-audio", "--no-first-run"]


def ctx(pw):
    """启动持久化浏览器上下文（缺 chromium 时自动退回 Edge）"""
    kwargs = dict(headless=False, user_agent=UA,
                  viewport={"width": 1440, "height": 900}, args=LAUNCH_ARGS)
    try:
        return pw.chromium.launch_persistent_context(str(PROFILE_DIR), **kwargs)
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        print("  ⚠ 自带 chromium 缺失，退回本机 Edge 启动", flush=True)
        return pw.chromium.launch_persistent_context(str(PROFILE_DIR), channel="msedge", **kwargs)


PROBE_JS = """
async () => {
  const r = await fetch('/aweme/v1/web/search/item/?keyword=%E7%94%B5%E5%8A%A8%E8%BD%AE%E6%A4%85&count=1&aid=6383&device_platform=webapp',
                        {credentials: 'include'});
  const t = await r.text();
  try {
    const j = JSON.parse(t);
    return {status: j.status_code, has_data: !!(j.data && j.data.length)};
  } catch (e) { return {status: -1, empty: true}; }
}
"""


def probe_search(page, keyword: str = "测试") -> tuple[bool, str]:
    """功能性登录探测：走搜索页自身发的接口判定（业务真正依赖的那条路）

    与 AutoAYH probe_search 同款：打开搜索页 → 拦截 /aweme/v1/web/search/item/ 响应。
    20s 硬上限，绝不无限等。
    """
    import json
    import urllib.parse
    seen: dict = {}

    def on_resp(resp):
        if "aweme/v1/web/search/" not in resp.url or seen:
            return
        try:
            j = json.loads(resp.text())
        except Exception as exc:
            seen["parse"] = str(exc)[:60]
            return
        if "data" in j or j.get("status_code") is not None:
            seen["status"] = j.get("status_code")
            seen["msg"] = j.get("status_msg") or ""
            seen["n"] = len(j.get("data") or [])

    try:
        page.on("response", on_resp)
        page.goto("https://www.douyin.com/search/" + urllib.parse.quote(keyword) + "?type=video",
                  wait_until="domcontentloaded", timeout=45000)
        for _ in range(5):
            page.wait_for_timeout(4000)
            if seen:
                break
        page.remove_listener("response", on_resp)
    except Exception as exc:
        return False, f"探测失败: {str(exc)[:80]}"

    if not seen:
        return False, "搜索页 20s 内没有返回搜索结果（可能未登录 / 被风控 / 网络异常）"
    if seen.get("status") == 0:
        return True, f"搜索可用 ✓（{seen.get('n', 0)} 条）"
    if seen.get("status") == 2483:
        return False, "搜索要求登录（请先登录，再继续搜索吧）"
    return False, f"搜索异常 status={seen.get('status')} {seen.get('msg')}"


def ensure_login() -> bool:
    """检测登录态（搜索页拦截法，比 cookie / 裸 fetch 准）"""
    from playwright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("✗ 没有浏览器配置，请先运行: python s1_trend/browser.py --login", flush=True)
        return False

    with sync_playwright() as pw:
        c = ctx(pw)
        try:
            page = c.new_page()
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            ok, why = probe_search(page)
            print(f"{'✓' if ok else '✗'} {why}", flush=True)
            return ok
        finally:
            c.close()


def qr_login(minutes: int = 10):
    """二维码扫码登录（每 25 秒自动刷新）——窗口可见，供用户扫码"""
    import time
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + minutes * 60

    # 登录时必须窗口可见（不能移屏外，否则扫不到码）
    visible_args = [a for a in LAUNCH_ARGS if not a.startswith("--window-position")]

    with sync_playwright() as pw:
        kwargs = dict(headless=False, user_agent=UA,
                      viewport={"width": 1440, "height": 900}, args=visible_args)
        try:
            c = pw.chromium.launch_persistent_context(str(PROFILE_DIR), **kwargs)
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            print("  ⚠ 自带 chromium 缺失，退回本机 Edge 启动", flush=True)
            c = pw.chromium.launch_persistent_context(str(PROFILE_DIR), channel="msedge", **kwargs)

        try:
            page = c.new_page()
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            # 点登录按钮
            try:
                page.click("text=登录", timeout=5000)
            except Exception:
                pass

            last_refresh = time.time()
            while time.time() < deadline:
                page.wait_for_timeout(5000)
                # 每 25 秒刷新二维码
                if time.time() - last_refresh > 25:
                    try:
                        page.reload(wait_until="domcontentloaded")
                        page.wait_for_timeout(2000)
                        page.click("text=登录", timeout=5000)
                    except Exception:
                        pass
                    last_refresh = time.time()

                # 检测登录状态
                result = page.evaluate(PROBE_JS)
                if result.get("status") == 0:
                    print("✓ 扫码成功，登录态已保存", flush=True)
                    return True
                print("  等待扫码...", flush=True)

            print("✗ 超时未扫码", flush=True)
            return False
        finally:
            c.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="抖音浏览器登录工具")
    parser.add_argument("--login", action="store_true", help="扫码登录")
    parser.add_argument("--check", action="store_true", help="检测登录态")
    parser.add_argument("--minutes", type=int, default=10, help="扫码等待分钟数")
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if ensure_login() else 1)
    elif args.login:
        sys.exit(0 if qr_login(args.minutes) else 1)
    else:
        parser.print_help()
