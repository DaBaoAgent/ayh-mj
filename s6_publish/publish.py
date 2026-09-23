"""发布编排：国内3平台（PostFlow）+ 海外6平台（Upload-Post）

国内通道：复用 AutoAYH 的 PostFlow CLI（vendor/postflow，douyin/xiaohongshu/tencent=视频号）
海外通道：s6_publish/uploadpost.py（REST 客户端）

用法：
    python s6_publish/publish.py --list                                # 看可发任务
    python s6_publish/publish.py --job <uid> --platform douyin          # 国内演练
    python s6_publish/publish.py --job <uid> --platform douyin --yes    # 国内真发
    python s6_publish/publish.py --job <uid> --platform instagram --yes # 海外真发
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from lib import CONFIG_DIR, STATE_DIR
from lib.state import connect, get_job, update_job, list_jobs

# PostFlow CLI（AutoAYH vendor）
POSTFLOW_DIR = Path("D:/@kaifa/AutoAYH/pipeline/vendor/postflow")
POSTFLOW_EXE = POSTFLOW_DIR / ".venv" / "Scripts" / "postflow.exe"

# 平台映射：我们的名字 → (通道, PostFlow子命令)
DOMESTIC = {
    "douyin": "douyin",
    "xiaohongshu": "xiaohongshu",
    "shipinhao": "tencent",
}
OVERSEAS = ["tiktok", "youtube", "instagram", "facebook", "telegram", "x"]

PACING_FILE = STATE_DIR / "publish_pacing.json"


def load_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "pipeline.yaml").read_text(encoding="utf-8"))


def load_pacing() -> dict:
    if PACING_FILE.exists():
        return json.loads(PACING_FILE.read_text(encoding="utf-8"))
    return {}


def save_pacing(data: dict):
    PACING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def check_quota(platform: str) -> tuple[bool, str]:
    """检查发布配额（窗口/限流/间隔）"""
    config = load_config()
    pub = config.get("publish", {})

    # 晚间静默 23:00-07:00
    now = datetime.now()
    if now.hour >= 23 or now.hour < 7:
        return False, "夜间静默期（23:00-07:00）"

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


def publish_domestic(uid: str, platform: str, job: dict, yes: bool = False) -> dict:
    """国内平台发布（PostFlow CLI）"""
    if platform not in DOMESTIC:
        raise ValueError(f"不支持的国内平台: {platform}")

    config = load_config()
    plat_cfg = config.get("publish", {}).get("domestic", {})
    account = plat_cfg.get("account_name", "ayh-main")

    video = job["video_path"]
    title = "轻便侠218电动轮椅"  # TODO: 从 jobs 读发布文案
    tags = "电动轮椅,老年代步,出行辅具"

    subcmd = DOMESTIC[platform]
    cmd = [
        str(POSTFLOW_EXE), subcmd, "upload-video",
        "--account", account,
        "--file", video,
        "--title", title,
        "--tags", tags,
        "--headed",
    ]

    if not yes:
        return {"platform": platform, "status": "dry_run", "cmd": " ".join(cmd)}

    ok, reason = check_quota(platform)
    if not ok:
        return {"platform": platform, "status": "quota_blocked", "reason": reason}

    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=900,
                            cwd=str(POSTFLOW_DIR))
    success = result.returncode == 0

    if success:
        mark_published(platform)

    # 记录发布
    with connect() as conn:
        conn.execute("""
            INSERT INTO publishes (job_id, platform, status, error)
            VALUES ((SELECT id FROM jobs WHERE uid = ?), ?, ?, ?)
        """, (uid, platform, "success" if success else "failed",
              None if success else (result.stderr or "")[-200:]))
        conn.commit()

    return {"platform": platform,
            "status": "success" if success else "failed",
            "output": (result.stdout or "")[-300:],
            "error": (result.stderr or "")[-300:] if not success else None}


def publish_overseas(uid: str, platform: str, job: dict, yes: bool = False) -> dict:
    """海外平台发布（Upload-Post）"""
    if platform not in OVERSEAS:
        raise ValueError(f"不支持的海外平台: {platform}")

    from s6_publish import uploadpost

    video = job["video_path"]
    title = "轻便侠218电动轮椅"  # TODO: 从 jobs 读发布文案

    if not yes:
        return {"platform": platform, "status": "dry_run",
                "video": video, "title": title}

    ok, reason = check_quota(platform)
    if not ok:
        return {"platform": platform, "status": "quota_blocked", "reason": reason}

    try:
        result = uploadpost.upload_video(
            video, title, [platform],
            tiktok_post_mode="MEDIA_UPLOAD",
            youtube_privacy="public",
        )
        request_id = result.get("request_id")
        final = uploadpost.wait_upload(request_id, timeout_s=900) if request_id else result
        status = "success"
        mark_published(platform)
    except Exception as e:
        final = {"error": str(e)[:300]}
        status = "failed"

    with connect() as conn:
        conn.execute("""
            INSERT INTO publishes (job_id, platform, status, error)
            VALUES ((SELECT id FROM jobs WHERE uid = ?), ?, ?, ?)
        """, (uid, platform, status,
              None if status == "success" else json.dumps(final, ensure_ascii=False)[:200]))
        conn.commit()

    return {"platform": platform, "status": status, "result": final}


def publish_job(uid: str, platforms: list[str], yes: bool = False) -> dict:
    """发布一个任务到多平台"""
    job = get_job(uid)
    if not job:
        raise ValueError(f"任务不存在: {uid}")
    if job["status"] != "ready":
        raise ValueError(f"任务 {uid} 状态是 {job['status']}，不是 ready（先跑 s5_compose）")
    if not job.get("video_path") or not Path(job["video_path"]).exists():
        raise ValueError(f"任务 {uid} 成片文件缺失")

    results = []
    for platform in platforms:
        if platform in DOMESTIC:
            r = publish_domestic(uid, platform, job, yes)
        elif platform in OVERSEAS:
            r = publish_overseas(uid, platform, job, yes)
        else:
            r = {"platform": platform, "status": "unknown_platform"}
        results.append(r)
        print(f"  {platform}: {r['status']}", flush=True)

        # 平台间留间隔（真发时）
        if yes and platform != platforms[-1]:
            gap = 30
            print(f"    等待 {gap}s 再发下一个平台...", flush=True)
            time.sleep(gap)

    # 全部成功 → 标记已发布
    if yes and all(r["status"] == "success" for r in results):
        update_job(uid, status="published",
                   publish_results=json.dumps(results, ensure_ascii=False),
                   published_at=datetime.now().isoformat())

    return {"uid": uid, "results": results,
            "all_success": all(r["status"] == "success" for r in results)}


def show_list():
    """列出可发布任务"""
    jobs = list_jobs("ready", limit=20)
    print(f"📋 待发布任务: {len(jobs)} 个")
    for j in jobs:
        print(f"  [{j['uid']}] {j.get('duration', 0):.1f}s {j.get('video_path', '')}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="发布编排")
    parser.add_argument("--list", action="store_true", help="列出可发任务")
    parser.add_argument("--job", help="任务UID")
    parser.add_argument("--platform", help="单个平台")
    parser.add_argument("--platforms", help="多平台（逗号分隔）")
    parser.add_argument("--yes", action="store_true", help="真发（默认演练）")
    args = parser.parse_args()

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

    if not platforms:
        parser.print_help()
        return 1

    mode = "真发" if args.yes else "演练"
    print(f"📤 发布 {args.job} → {', '.join(platforms)}（{mode}）", flush=True)
    result = publish_job(args.job, platforms, yes=args.yes)
    print(json.dumps(result, ensure_ascii=False, indent=1)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
