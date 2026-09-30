"""发布编排（Phase 10 重写）：Packaging artifact + canonical JobStore + 发布 Gate。

国内通道：PostFlow CLI（vendor/postflow：douyin / xiaohongshu / tencent=视频号）
海外通道：s6_publish/uploadpost.py（Upload-Post REST）

Phase 10 起本文件**不再写死任何标题/标签**：所有对外文案来自每条视频的
packaging artifact（`out/gen_<uid>/packaging.json`，由 PackagingAgent 生成）；
发布状态写进 canonical `publish_records`（JobStore），不再另立一套 jobs 状态。

本文件只做两件事：
  · 提供 `check_quota` / `mark_published` / `load_pacing` 这些**本机限流**事实（窗口/上限/间隔）；
  · 提供 `CliPublishAdapter` 把一次发布落到真实通道。
  编排本身（状态机、幂等、按平台记录、Gate）在 `lib.orchestrator.publishing.PublishService`。

用法：
    python s6_publish/publish.py --list                       # 看可发任务
    python s6_publish/publish.py --job <uid>                  # 演练（只出计划，不改状态）
    python s6_publish/publish.py --job <uid> --yes            # 按 packaging 里的模式发布
    python s6_publish/publish.py --job <uid> --platform x --yes
    python s6_publish/publish.py --pause douyin --reason "账号异常"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import STATE_DIR, packaging
from lib.orchestrator.errors import AUTH_EXPIRED
from lib.orchestrator.publishing import (
    DRAFT,
    FAILED,
    SUCCESS,
    PublishService,
)
from lib.settings import get_settings

# PostFlow CLI（ayh-mj 自有 vendor，2026-09-25 从 AutoAYH 迁入）
POSTFLOW_DIR = get_settings().postflow_dir
POSTFLOW_EXE = POSTFLOW_DIR / ".venv" / "Scripts" / "postflow.exe"

# 平台映射：我们的名字 → (通道, PostFlow子命令)
DOMESTIC = {
    "douyin": "douyin",
    "xiaohongshu": "xiaohongshu",
    "shipinhao": "tencent",
}
OVERSEAS = ["tiktok", "youtube", "instagram", "facebook", "telegram", "x"]

PACING_FILE = STATE_DIR / "publish_pacing.json"

ROOT = get_settings().root

# AUTH_EXPIRED 判定：CLI/REST 的错误文本里出现这些就认为凭据失效（不猜别的）
_AUTH_MARKERS = ("登录", "扫码", "未登录", "认证失效", "token expired", "unauthorized",
                 "401", "auth", "credential", "cookie")


def load_config() -> dict:
    """配置唯一来源：lib.settings（config/default.yaml + AYHMJ_* 环境变量）。"""
    s = get_settings()
    return {
        "publish": s.publish.model_dump(),
        "engage": s.engage.model_dump(),
        "product": s.product.model_dump(),
        "webui": s.webui.model_dump(),
    }


def load_pacing() -> dict:
    if PACING_FILE.exists():
        return json.loads(PACING_FILE.read_text(encoding="utf-8"))
    return {}


def save_pacing(data: dict):
    PACING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PACING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def check_quota(platform: str) -> tuple[bool, str]:
    """检查发布配额（窗口/限流/间隔）。平台被熔断暂停时一律不放行。"""
    reason = packaging.pause_reason(ROOT, platform)
    if reason:
        return False, f"平台已暂停：{reason}"

    config = load_config()
    pub = config.get("publish", {})

    # 晚间静默（可配置，默认 23:00-07:00）
    now = datetime.now()
    silence = pub.get("night_silence") or {"start": "23:00", "end": "07:00"}
    s_start, s_end = silence.get("start", "23:00"), silence.get("end", "07:00")
    hhmm = now.strftime("%H:%M")
    if s_start > s_end:            # 跨零点
        if hhmm >= s_start or hhmm < s_end:
            return False, f"夜间静默期（{s_start}-{s_end}）"
    elif s_start <= hhmm < s_end:
        return False, f"夜间静默期（{s_start}-{s_end}）"

    # 发布窗口
    windows = pub.get("publish_windows", [])
    if windows:
        in_window = False
        for w in windows:
            start = w.get("start", "00:00")
            end = w.get("end", "23:59")
            if start <= now.strftime("%H:%M") <= end:
                in_window = True
                break
        if not in_window:
            return False, f"不在发布窗口（{', '.join(w['start']+'-'+w['end'] for w in windows)}）"

    # 每日上限
    pacing = load_pacing()
    today = now.strftime("%Y-%m-%d")
    today_count = pacing.get(f"{today}:{platform}", 0)
    daily_limit = pub.get("daily_limit", 6)
    if today_count >= daily_limit:
        return False, f"今日已达上限（{today_count}/{daily_limit}）"

    # 最小间隔
    last_key = f"last:{platform}"
    if last_key in pacing:
        last_time = datetime.fromisoformat(pacing[last_key])
        gap_min = (now - last_time).total_seconds() / 60
        min_gap = pub.get("min_interval_minutes", 30)
        if gap_min < min_gap:
            return False, f"距上次发布仅 {gap_min:.0f} 分钟（需 {min_gap} 分钟）"

    return True, "OK"


def mark_published(platform: str):
    """记录发布（配额计数）"""
    pacing = load_pacing()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    key = f"{today}:{platform}"
    pacing[key] = pacing.get(key, 0) + 1
    pacing[f"last:{platform}"] = now.isoformat()
    save_pacing(pacing)


def _is_auth_error(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in _AUTH_MARKERS)


def _run_cli(cmd: list[str], timeout: float = 900.0) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [str(c) for c in cmd], capture_output=True, text=True, errors="replace",
        timeout=timeout, cwd=str(Path(__file__).resolve().parent.parent))


class CliPublishAdapter:
    """真实发布适配器 —— 文案只来自 packaging，模式只来自 gate 的裁决。

    `draft` 模式是"声明无法程序化确认"时的**唯一**允许路径：
      · 国内：要求 `publish.domestic_draft_args` 显式配置（无法确认 PostFlow 的草稿参数就
        拒绝执行，绝不退化成直发）；
      · 海外：tiktok 走 MEDIA_UPLOAD（进创作者收件箱）、youtube 走 privacy=private。
    `direct` 只会在 gate 已确认该平台声明可程序化提交时出现。
    """

    def __init__(self, *, runner=None, uploadpost=None) -> None:
        self._runner = runner or _run_cli
        self._uploadpost = uploadpost

    # ── 通道 ───────────────────────────────────────────────────
    def publish(self, *, uid: str, job: dict, brief: dict, platform: str,
                copy: dict, mode: str) -> dict:
        policy = packaging.policy_for(platform)
        if policy is None:
            return {"status": FAILED, "error": f"未知平台：{platform}"}
        if mode == "require_human":
            return {"status": FAILED, "error": "该平台声明无法确认且无草稿通道，需人工发布"}
        if policy.channel == "domestic":
            return self._domestic(uid, job, platform, copy, mode)
        return self._overseas(uid, job, platform, copy, mode)

    def _domestic(self, uid: str, job: dict, platform: str, copy: dict, mode: str) -> dict:
        pub = load_config().get("publish", {})
        account = (pub.get("domestic", {}) or {}).get("account_name", "ayh-main")
        draft_args = list(pub.get("domestic_draft_args") or [])
        if mode == "draft" and not draft_args:
            return {"status": FAILED,
                    "error": ("无法确认 PostFlow 的草稿参数：请先配置 "
                              "publish.domestic_draft_args（未配置前不允许直发 AI 内容）")}
        extra = draft_args if mode == "draft" else []
        cmd = [str(POSTFLOW_EXE), DOMESTIC[platform], "upload-video",
               "--account", account,
               "--video", str(job.get("video_path") or ""),
               "--title", copy["title"],
               "--desc", copy["description"],
               "--tags", ",".join(copy["hashtags"]),
               *extra]
        try:
            result = self._runner(cmd)
        except Exception as exc:
            return {"status": FAILED, "error": f"{type(exc).__name__}: {exc}"}
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode != 0 or _is_auth_error(text):
            status = AUTH_EXPIRED if _is_auth_error(text) else FAILED
            return {"status": status, "error": text.strip()[-300:]}
        return {"status": DRAFT if mode == "draft" else SUCCESS,
                "detail": text.strip()[-300:]}

    def _overseas(self, uid: str, job: dict, platform: str, copy: dict, mode: str) -> dict:
        uploadpost = self._uploadpost
        if uploadpost is None:
            from s6_publish import uploadpost as uploadpost_mod
            uploadpost = uploadpost_mod
        opts: dict = {}
        if platform == "tiktok":
            opts["tiktok_post_mode"] = "MEDIA_UPLOAD" if mode == "draft" else "DIRECT_POST"
        if platform == "youtube":
            opts["youtube_privacy"] = "private" if mode == "draft" else "public"
        try:
            result = uploadpost.upload_video(
                str(job.get("video_path") or ""), copy["title"], [platform], **opts)
            request_id = (result or {}).get("request_id")
            final = uploadpost.wait_upload(request_id, timeout_s=900) if request_id else result
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            return {"status": AUTH_EXPIRED if _is_auth_error(msg) else FAILED, "error": msg}
        return {"status": DRAFT if mode == "draft" else SUCCESS,
                "post_id": (final or {}).get("post_id"),
                "post_url": (final or {}).get("post_url"),
                "detail": json.dumps(final, ensure_ascii=False)[:300]}


def publish_job(uid: str, platforms: list[str], yes: bool = False) -> dict:
    """发布一个任务到多平台（编排在 PublishService；这里只是构造 + 调用）。"""
    service = PublishService(adapter=CliPublishAdapter(), root=ROOT)
    return service.publish(uid, platforms=platforms or None, real=bool(yes))


def show_list():
    """列出可发布任务（canonical JobStore 的 READY）。"""
    from lib.jobstore import JobState, store

    jobs = store.list_jobs(JobState.READY, limit=20)
    print(f"📋 待发布任务: {len(jobs)} 个")
    for j in jobs:
        uid = str(j.get("uid"))
        brief = packaging.load_brief(ROOT, uid)
        modes = sorted({t.get("mode") for t in (brief or {}).get("targets") or []})
        print(f"  [{uid}] {j.get('duration') or ''} {j.get('video_path') or ''}"
              f" | packaging={'有' if brief else '缺失'} modes={modes or '-'}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="发布编排")
    parser.add_argument("--list", action="store_true", help="列出可发任务")
    parser.add_argument("--job", help="任务UID")
    parser.add_argument("--platform", help="单个平台")
    parser.add_argument("--platforms", help="多平台（逗号分隔）")
    parser.add_argument("--yes", action="store_true", help="真发（默认演练）")
    parser.add_argument("--pause", help="暂停某平台（凭据/账号异常）")
    parser.add_argument("--resume", help="解除某平台暂停（人工确认后）")
    parser.add_argument("--reason", default="", help="暂停原因")
    args = parser.parse_args()

    if args.pause:
        packaging.pause_platform(ROOT, args.pause, args.reason or "人工暂停")
        print(f"⏸ 已暂停 {args.pause}：{args.reason or '人工暂停'}")
        return 0
    if args.resume:
        ok = packaging.resume_platform(ROOT, args.resume)
        print(f"{'▶ 已恢复' if ok else 'ℹ 未处于暂停状态'} {args.resume}")
        return 0

    if args.list:
        show_list()
        return 0

    if not args.job:
        parser.print_help()
        return 1

    platforms = []
    if args.platform:
        platforms = [args.platform]
    elif args.platforms:
        platforms = args.platforms.split(",")

    mode = "真发" if args.yes else "演练"
    print(f"📤 发布 {args.job} → {', '.join(platforms) or '（packaging 目标）'}（{mode}）",
          flush=True)
    result = publish_job(args.job, platforms, yes=args.yes)
    print(json.dumps(result, ensure_ascii=False, indent=1)[:2000])
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
