#!/usr/bin/env python3
"""Upload-Post 客户端 —— 海外 6 平台自动发布 + 评论私信维护。

来源：dabao 技能（DaBaoAgent/dabao，AutoYY 推广流程）里的 Upload-Post MCP 能力，
这里落成 Python REST 客户端，供 ayh-mj 发布/互动模块直接调用。

平台值（platform[]）：tiktok / youtube / instagram / x / threads / telegram / facebook /
linkedin / pinterest / bluesky 等 13+。

凭据（**不进仓库**）：UPLOADPOST_API_KEY 环境变量，或 Windows 凭据库
（keyring service="uploadpost", username="api_key"）。

用法：
    python s7_publish/uploadpost.py whoami                      # 验通
    python s7_publish/uploadpost.py upload --file x.mp4 --title "标题" --platforms tiktok,youtube
    python s7_publish/uploadpost.py status --request-id xxx
    python s7_publish/uploadpost.py comments --platform youtube --post-id xxx
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import httpx
except ImportError:  # pragma: no cover
    print("需要 httpx：.venv/Scripts/python.exe -m pip install httpx", file=sys.stderr)
    raise

API = "https://api.upload-post.com/api"
KEYRING_SERVICE = "uploadpost"
KEYRING_USER = "api_key"

# 海外 6 平台（用户 dabao 项目里那套）
OVERSEAS_PLATFORMS = ["tiktok", "youtube", "instagram", "x", "threads", "telegram"]


# ---------------------------------------------------------------- 凭据

def api_key() -> str:
    """API Key 解析：环境变量 → Windows 凭据库。绝不落盘。"""
    k = os.environ.get("UPLOADPOST_API_KEY")
    if k:
        return k.strip()
    try:
        import keyring  # type: ignore
        k = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if k:
            return k.strip()
    except Exception:
        pass
    raise SystemExit(
        "找不到 Upload-Post API Key。二选一：\n"
        "  1) setx UPLOADPOST_API_KEY \"<你的key>\"   （新开终端生效）\n"
        "  2) python -c \"import keyring;keyring.set_password('uploadpost','api_key','<key>')\"\n"
        "Key 在 https://app.upload-post.com → API Keys 页面。"
    )


def default_profile() -> str:
    """profile 解析：环境变量 UPLOADPOST_PROFILE → config/pipeline.yaml 的 uploadpost.profile。

    **不再有内置默认值**：早期版本默认 'xiangge'，结果没配 profile 时会悄悄发到别人的账号上。
    现在没配就明确报错，绝不猜。
    """
    if (v := os.environ.get("UPLOADPOST_PROFILE")):
        return v.strip()
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8")) or {}
        v = (((cfg.get("publish") or {}).get("overseas") or {}).get("profile") or "").strip()
        if v:
            return v
    except Exception:
        pass
    raise SystemExit(
        "还没配置 Upload-Post profile。二选一：\n"
        "  1) 改 config/pipeline.yaml 的 uploadpost.profile: \"<profile名>\"\n"
        "  2) setx UPLOADPOST_PROFILE \"<profile名>\"\n"
        "（profile 是 Upload-Post 后台里的子账号名，与各平台 @handle 不同）")


def _headers(json_body: bool = False) -> dict:
    h = {"Authorization": f"Apikey {api_key()}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


class UploadPostError(RuntimeError):
    pass


def _check(r: httpx.Response) -> dict:
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:400]}
    if r.status_code >= 400 or (isinstance(body, dict) and body.get("success") is False):
        raise UploadPostError(f"HTTP {r.status_code}: {json.dumps(body, ensure_ascii=False)[:400]}")
    return body if isinstance(body, dict) else {"data": body}


# ---------------------------------------------------------------- 账号

def whoami() -> dict:
    """GET /api/uploadposts/me —— 验通 + 看套餐用量。"""
    return _check(httpx.get(f"{API}/uploadposts/me", headers=_headers(), timeout=30))


# ---------------------------------------------------------------- 发布

def upload_video(
    video: str | Path,
    title: str,
    platforms: list[str],
    profile: str | None = None,
    description: str | None = None,
    first_comment: str | None = None,
    scheduled_date: str | None = None,
    timezone: str | None = None,
    external_id: str | None = None,
    tiktok_post_mode: str | None = None,
    youtube_privacy: str | None = None,
    extra: dict | None = None,
    async_upload: bool = True,
) -> dict:
    """POST /api/upload —— 一条视频发多平台。

    tiktok_post_mode: MEDIA_UPLOAD（草稿箱，默认推荐，保自然流量）/ DIRECT_POST
    youtube_privacy:  public / unlisted / private
    """
    profile = profile or default_profile()
    p = Path(video)
    if not p.exists():
        raise UploadPostError(f"视频不存在：{p}")

    data: list[tuple[str, str]] = [("user", profile), ("title", title)]
    for plat in platforms:
        data.append(("platform[]", plat))
    if description:
        data.append(("description", description))
    if first_comment:
        data.append(("first_comment", first_comment))
    if scheduled_date:
        data.append(("scheduled_date", scheduled_date))
        if timezone:
            data.append(("timezone", timezone))
    if external_id:
        data.append(("external_id", external_id))
    if tiktok_post_mode and "tiktok" in platforms:
        data.append(("tiktok_post_mode", tiktok_post_mode))
    if youtube_privacy and "youtube" in platforms:
        data.append(("youtube_privacy_status", youtube_privacy))
    for k, v in (extra or {}).items():
        data.append((k, str(v)))
    if async_upload:
        data.append(("async_upload", "true"))

    with p.open("rb") as fh:
        files = {"video": (p.name, fh, "video/mp4")}
        r = httpx.post(f"{API}/upload", headers=_headers(), data=data, files=files, timeout=900)
    return _check(r)


def upload_status(request_id: str) -> dict:
    """GET /api/uploadposts/status?request_id= —— 轮询上传结果。"""
    return _check(httpx.get(f"{API}/uploadposts/status",
                            params={"request_id": request_id}, headers=_headers(), timeout=60))


def wait_upload(request_id: str, timeout_s: int = 900, interval: int = 10) -> dict:
    """轮询到全部平台完成。状态缓存 2–5s，官方建议 ≥5s 一次。"""
    t0 = time.time()
    last: dict = {}
    while time.time() - t0 < timeout_s:
        last = upload_status(request_id)
        res = last.get("results") or last.get("platforms") or {}
        states = [str((v or {}).get("status", "")).lower() for v in res.values()] if isinstance(res, dict) else []
        if states and all(s in ("completed", "success", "failed", "skipped", "published") for s in states):
            return last
        if str(last.get("status", "")).lower() in ("completed", "success", "failed"):
            return last
        time.sleep(max(5, interval))
    return last


def history(platform: str | None = None, profile: str | None = None, limit: int = 20) -> dict:
    """GET /api/uploadposts/history —— 已发布列表（拿 permalink/post_id）。"""
    profile = profile or default_profile()
    params: dict = {"user": profile, "limit": limit}
    if platform:
        params["platform"] = platform
    return _check(httpx.get(f"{API}/uploadposts/history", params=params, headers=_headers(), timeout=60))


# ---------------------------------------------------------------- 评论

def comments(platform: str, post_id: str | None = None, post_url: str | None = None,
             profile: str | None = None, limit: int = 30, after: str | None = None,
             comment_id: str | None = None) -> dict:
    """GET /api/uploadposts/comments —— 读评论。

    注意：TikTok 的 limit 上限 30；TikTok 评论只能读不能回（回复需 create_comment 且限自己视频）。
    """
    profile = profile or default_profile()
    params: dict = {"platform": platform, "user": profile, "limit": min(limit, 30)}
    if post_id:
        params["post_id"] = str(post_id)
    if post_url:
        params["post_url"] = post_url
    if after:
        params["after"] = after
    if comment_id:
        params["comment_id"] = str(comment_id)
    return _check(httpx.get(f"{API}/uploadposts/comments", params=params, headers=_headers(), timeout=60))


def create_comment(platform: str, text: str, post_id: str | None = None,
                   post_url: str | None = None, comment_id: str | None = None,
                   profile: str | None = None) -> dict:
    """POST /api/uploadposts/comments —— 发评论/回复。

    comment_id → 回复某条评论；post_id/post_url → 发顶层评论。
    Instagram 只能回复（必须带 comment_id）；TikTok 必须带 post_id。
    """
    profile = profile or default_profile()
    body: dict = {"platform": platform, "user": profile, "text": text}
    if post_id:
        body["post_id"] = str(post_id)
    if post_url:
        body["post_url"] = post_url
    if comment_id:
        body["comment_id"] = str(comment_id)
    return _check(httpx.post(f"{API}/uploadposts/comments", headers=_headers(json_body=True),
                             json=body, timeout=60))


# ---------------------------------------------------------------- 私信（DM）

def dm_conversations(platform: str = "instagram", profile: str | None = None) -> dict:
    """GET /api/uploadposts/dms/conversations —— 读私信会话（目前仅 Instagram）。"""
    profile = profile or default_profile()
    return _check(httpx.get(f"{API}/uploadposts/dms/conversations",
                            params={"platform": platform, "user": profile},
                            headers=_headers(), timeout=60))


def dm_send(recipient_id: str, message: str, platform: str = "instagram",
            profile: str | None = None, buttons: list[dict] | None = None) -> dict:
    """POST /api/uploadposts/dms/send —— 发私信（IG 支持按钮，title ≤20 字）。"""
    profile = profile or default_profile()
    body: dict = {"platform": platform, "user": profile,
                  "recipient_id": str(recipient_id), "message": message}
    if buttons:
        body["buttons"] = buttons[:3]
    return _check(httpx.post(f"{API}/uploadposts/dms/send", headers=_headers(json_body=True),
                             json=body, timeout=60))


# ---------------------------------------------------------------- AutoDM（关键词自动私信）

def autodm_start(post_url: str, reply_message: str, trigger_keywords: list[str] | None = None,
                 buttons: list[dict] | None = None, profile: str | None = None,
                 interval: int = 15) -> dict:
    """启动 AutoDM 监控：新评论命中关键词 → 自动私信。每 profile 每天最多 2 个，15 天自动过期。"""
    profile = profile or default_profile()
    body: dict = {"post_url": post_url, "reply_message": reply_message,
                  "profile_username": profile, "monitoring_interval": max(15, interval)}
    if trigger_keywords:
        body["trigger_keywords"] = trigger_keywords
    if buttons:
        body["buttons"] = buttons[:3]
    return _check(httpx.post(f"{API}/uploadposts/autodms/start", headers=_headers(json_body=True),
                             json=body, timeout=60))


def autodm_status(include_inactive: bool = False) -> dict:
    return _check(httpx.get(f"{API}/uploadposts/autodms/status",
                            params={"include_inactive": str(include_inactive).lower()},
                            headers=_headers(), timeout=60))


def autodm_action(action: str, monitor_id: str) -> dict:
    """action ∈ pause / resume / stop / delete。"""
    if action not in ("pause", "resume", "stop", "delete"):
        raise UploadPostError(f"未知 action: {action}")
    return _check(httpx.post(f"{API}/uploadposts/autodms/{action}", headers=_headers(json_body=True),
                             json={"monitor_id": monitor_id}, timeout=60))


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="Upload-Post 客户端（海外发布 + 评论私信）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="验通 + 套餐用量")

    u = sub.add_parser("upload", help="上传视频")
    u.add_argument("--file", required=True)
    u.add_argument("--title", required=True)
    u.add_argument("--platforms", default=",".join(OVERSEAS_PLATFORMS))
    u.add_argument("--profile", default=None, help="Upload-Post profile 名（默认取配置）")
    u.add_argument("--description", default=None)
    u.add_argument("--first-comment", default=None)
    u.add_argument("--scheduled-date", default=None)
    u.add_argument("--tiktok-mode", default="MEDIA_UPLOAD")
    u.add_argument("--youtube-privacy", default="public")
    u.add_argument("--wait", action="store_true", help="轮询到完成")

    s = sub.add_parser("status", help="查上传状态")
    s.add_argument("--request-id", required=True)

    c = sub.add_parser("comments", help="读评论")
    c.add_argument("--platform", required=True)
    c.add_argument("--post-id", default=None)
    c.add_argument("--post-url", default=None)
    c.add_argument("--limit", type=int, default=30)

    h = sub.add_parser("history", help="已发布列表")
    h.add_argument("--platform", default=None)
    h.add_argument("--limit", type=int, default=20)

    a = sub.add_parser("autodm", help="AutoDM 监控")
    a.add_argument("--action", default="status", choices=["status", "start", "pause", "resume", "stop"])
    a.add_argument("--post-url", default=None)
    a.add_argument("--message", default=None)
    a.add_argument("--keywords", default=None)
    a.add_argument("--monitor-id", default=None)

    args = ap.parse_args()

    if args.cmd == "whoami":
        r = whoami()
        uinfo = r.get("user") or r
        print(json.dumps(uinfo, ensure_ascii=False, indent=2)[:1200])
    elif args.cmd == "upload":
        r = upload_video(args.file, args.title, args.platforms.split(","), profile=args.profile,
                         description=args.description, first_comment=args.first_comment,
                         scheduled_date=args.scheduled_date, tiktok_post_mode=args.tiktok_mode,
                         youtube_privacy=args.youtube_privacy)
        print(json.dumps(r, ensure_ascii=False, indent=2)[:800])
        if args.wait and r.get("request_id"):
            print("—— 轮询 ——")
            print(json.dumps(wait_upload(r["request_id"]), ensure_ascii=False)[:1500])
    elif args.cmd == "status":
        print(json.dumps(upload_status(args.request_id), ensure_ascii=False, indent=2)[:2000])
    elif args.cmd == "comments":
        r = comments(args.platform, post_id=args.post_id, post_url=args.post_url, limit=args.limit)
        for c_ in (r.get("comments") or [])[:20]:
            who = (c_.get("user") or {}).get("username") or c_.get("username") or "?"
            print(f"[{c_.get('id')}] @{who}: {str(c_.get('text'))[:120]}")
        print(f"共 {len(r.get('comments') or [])} 条")
    elif args.cmd == "history":
        print(json.dumps(history(args.platform, limit=args.limit), ensure_ascii=False)[:2000])
    elif args.cmd == "autodm":
        if args.action == "status":
            print(json.dumps(autodm_status(True), ensure_ascii=False)[:1500])
        elif args.action == "start":
            kw = (args.keywords or "").split(",") if args.keywords else None
            print(json.dumps(autodm_start(args.post_url, args.message, kw), ensure_ascii=False)[:800])
        else:
            print(json.dumps(autodm_action(args.action, args.monitor_id), ensure_ascii=False)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
