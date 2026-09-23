"""全流程引擎 — 唯一执行入口（双模式）

模式（state/console.json 的 "mode" 字段）：
  · template（新链路）：热点 → 10套模板+选角+音色克隆出片 → 烧字幕 → 发布
  · legacy（旧链路）：s2 脚本 → split 分镜 → batch_gen → merge(TTS字幕) → 发布

用法：
    python tools/run_all.py                    # 全流程
    python tools/run_all.py --only trend,copy  # 只跑部分阶段（免费验证用）
    python tools/run_all.py --dry              # 演练（不出片不花钱）
    python tools/run_all.py --mode template    # 强制模板链路
"""
import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import STATE_DIR
from lib.state import create_job, list_jobs, update_job

# 状态文件
RUN_STATUS_FILE = STATE_DIR / "run_status.json"
RUN_PROGRESS_FILE = STATE_DIR / "run_progress.jsonl"

# 6 阶段
STAGES = ["trend", "copy", "storyboard", "generate", "compose", "publish"]

# 运行参数（由控制台写 state/console.json，这里读取）
CONSOLE_STATE_FILE = STATE_DIR / "console.json"


def load_console_state() -> dict:
    if CONSOLE_STATE_FILE.exists():
        return json.loads(CONSOLE_STATE_FILE.read_text(encoding="utf-8"))
    return {"daily_target": 3, "real_publish": False, "real_engage": False, "mode": "legacy"}


def console_mode() -> str:
    return load_console_state().get("mode", "legacy")


def log(message: str, level: str = "info"):
    """写日志到进度文件"""
    entry = {
        "type": "log",
        "level": level,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    with open(RUN_PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{level.upper()}] {message}", flush=True)


def update_status(running: bool, stage: str = None, progress: int = 0, message: str = ""):
    """更新运行状态"""
    status = {
        "running": running,
        "current_stage": stage,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now().isoformat(),
    }
    RUN_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")


# ============ 阶段实现 ============

def run_stage_trend(dry: bool = False):
    """阶段1: 热点爆款抓取"""
    log("🔥 抓取热点爆款（抖音热榜 + 关键词搜索）...")
    from s1_trend.run import run as trend_run
    result = trend_run()
    log(f"✓ 热点完成：入库 {result.get('saved', 0)} 条", "success")
    return True


def run_stage_copy(dry: bool = False):
    """阶段2: 文案生成"""
    log("📝 热点匹配分析 + 软广脚本生成...")
    from s2_copy.analyze import run_analysis
    from s2_copy.gen_script import generate

    target = load_console_state().get("daily_target", 3)
    analysis = run_analysis(limit=target * 5)
    log(f"  分析 {analysis.get('analyzed', 0)} 条，匹配 {analysis.get('matched', 0)} 条")

    scripts = generate(top=target)
    log(f"✓ 文案完成：生成 {scripts.get('generated', 0)} 个脚本", "success")
    return True


def _latest_hotspot() -> dict | None:
    """取匹配分最高且**未用过的**热点（全用过则退回最高分）"""
    from lib.ideas import used_hotspots
    from lib.state import connect
    used = used_hotspots()
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM trends WHERE matched = 1 ORDER BY score DESC LIMIT 20"
        ).fetchall()]
    for r in rows:
        if (r.get("title") or "") not in used:
            return r
    return rows[0] if rows else None


def run_stage_storyboard(dry: bool = False):
    """阶段3: 智能分镜"""
    target = load_console_state().get("daily_target", 3)

    if console_mode() == "template":
        log("🎬 模板分镜（10套模板轮换 + 热点绑定）...")
        from s3_storyboard.templates import adapt_lines, mark_used, pick_template, to_storyboard
        hot = _latest_hotspot()
        hot_title = hot["title"] if hot else ""
        if hot:
            log(f"  绑定热点：{hot_title[:40]}")

        done = 0
        for _ in range(max(1, target)):
            uid = create_job()
            tpl = pick_template()
            lines_result = adapt_lines(tpl, hot_title)
            sb = to_storyboard(tpl, lines_result["lines"], job_uid=uid)
            sb["hot_title"] = hot_title
            # 应用场景微调（LLM 让场景服务主打卖点）
            tw = lines_result.get("scene_tweaks") or {}
            for shot in sb["shots"]:
                t = tw.get(str(shot["seq"]))
                if t:
                    if t.get("start_state"):
                        shot["start_state"] = t["start_state"]
                    if t.get("end_state"):
                        shot["end_state"] = t["end_state"]
            # 角色组（宝哥规则：每条新视频换一组角色）——storyboard 阶段定组（审核可见，生成时同组）
            from lib.cast import _role_group_for
            rg = _role_group_for(uid)
            sb["role_group"] = rg["name"]
            sb["role_group_cast"] = {k: v for k, v in rg.items() if k != "name" and v}
            # 卖点轮换记录（宝哥规则：每条视频换一个卖点主打）
            sp = lines_result.get("sales_point")
            if sp:
                from lib.products import record_point
                record_point(sp["id"], uid)
                sb["sales_point"] = sp
            # 叙事思路记录（宝哥规则：每次不同的思路）
            ang = lines_result.get("angle")
            if ang:
                from lib.angles import record_angle
                record_angle(ang["id"], uid)
                sb["angle"] = ang
            sb_path = STATE_DIR / f"storyboard_{uid}.json"
            sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
            update_job(uid, status="storyboard", storyboard=json.dumps(sb, ensure_ascii=False))
            mark_used(tpl["id"])
            # 记录已用创意（防重复用点）
            from lib.ideas import record_idea
            record_idea(tpl["id"], tpl["name"], hot_title,
                        lines_result["lines"], lines_result.get("reason", ""))
            log(f"  ✓ {uid}: {tpl['id']} {tpl['name']}（{lines_result.get('reason', '')[:30]}）")
            done += 1
        log(f"✓ 分镜完成：{done} 个任务", "success")
        return True

    # legacy：旧分镜器
    log("🎬 智能分镜（legacy）...")
    from s3_storyboard.split import run as sb_run
    result = sb_run(top=target)
    log(f"✓ 分镜完成：{result.get('processed', 0)} 个任务", "success")
    return True


def run_stage_generate(dry: bool = False):
    """阶段4: H3视频生成"""
    target = load_console_state().get("daily_target", 3)

    if console_mode() == "template":
        log(f"🎥 模板链路出片（选角+音色克隆）{'（演练）' if dry else ''}...")
        from s4_generate.gen_from_storyboard import run as gen_run
        jobs = list_jobs("storyboard", limit=target)
        if not jobs:
            log("⚠ 没有待生成任务（status=storyboard）", "warning")
            return True
        done = 0
        for job in jobs:
            sb_path = STATE_DIR / f"storyboard_{job['uid']}.json"
            if not sb_path.exists():
                log(f"  ⚠ {job['uid']}: 缺分镜文件，跳过", "warning")
                continue
            if dry:
                log(f"  (演练) {job['uid']}")
                continue
            try:
                final = gen_run(str(sb_path))
                update_job(job["uid"], status="generate", video_path=str(final))
                log(f"  ✓ {job['uid']}: {final.name}", "success")
                done += 1
            except Exception as e:
                log(f"  ✗ {job['uid']}: {str(e)[:100]}", "error")
        log(f"✓ 生成完成：{done}/{len(jobs)}", "success")
        return True

    # legacy：batch_gen
    log(f"🎥 H3 视频生成（legacy）{'（演练）' if dry else ''}...")
    from s4_generate.batch_gen import run as gen_run
    result = gen_run(top=target, dry=dry)
    log(f"✓ 生成完成：{result.get('processed', 0)} 个任务", "success")
    return True


def run_stage_compose(dry: bool = False):
    """阶段5: 合成烧字幕"""
    if console_mode() == "template":
        log("🎞️ 模板链路烧字幕...")
        from s5_compose.burn_subtitles import burn
        jobs = list_jobs("generate", limit=10)
        if not jobs:
            log("⚠ 没有待装配任务", "warning")
            return True
        done = 0
        for job in jobs:
            sb_path = STATE_DIR / f"storyboard_{job['uid']}.json"
            video = job.get("video_path")
            if not video or not Path(video).exists():
                log(f"  ⚠ {job['uid']}: 缺视频文件", "warning")
                continue
            if dry:
                log(f"  (演练) {job['uid']}")
                continue
            try:
                lines = None
                if sb_path.exists():
                    sb = json.loads(sb_path.read_text(encoding="utf-8"))
                    lines = [s["narration"] for s in sb["shots"]]
                # 优先"按镜头时间轴对齐"烧录（字幕与对白精准匹配——宝哥规则）
                shots_dir = Path(video).parent / "shots"
                if lines and shots_dir.exists():
                    from s5_compose.burn_subtitles import burn_by_storyboard
                    sub = burn_by_storyboard(video, shots_dir, lines)
                else:
                    sub = burn(video, expected_lines=lines)
                update_job(job["uid"], status="ready", video_path=str(sub))
                log(f"  ✓ {job['uid']}: {sub.name}", "success")
                done += 1
            except Exception as e:
                log(f"  ✗ {job['uid']}: {str(e)[:100]}", "error")
        log(f"✓ 装配完成：{done}/{len(jobs)}", "success")
        return True

    # legacy：TTS+merge
    log("🎞️ 合成装配（legacy: TTS + 拼接 + 烧字幕）...")
    from s5_compose.merge import merge_job

    jobs = list_jobs("generate", limit=10)
    if not jobs:
        log("⚠ 没有待装配任务", "warning")
        return True

    done = 0
    for job in jobs:
        try:
            result = merge_job(job["uid"])
            log(f"  ✓ {job['uid']}: {result['duration']:.1f}s", "success")
            done += 1
        except Exception as e:
            log(f"  ✗ {job['uid']}: {str(e)[:80]}", "error")
    log(f"✓ 装配完成：{done}/{len(jobs)}", "success")
    return True


def run_stage_publish(dry: bool = False):
    """阶段6: 发布互动"""
    console = load_console_state()
    real = console.get("real_publish", False)
    real_engage = console.get("real_engage", False)
    yes = real and not dry
    log(f"📤 发布{'（真发）' if yes else '（演练）'}...")

    from s6_publish.publish import publish_job

    jobs = list_jobs("ready", limit=5)
    if not jobs:
        log("⚠ 没有待发布任务（status=ready）", "warning")
        return True

    platforms = console.get("publish_platforms") or ["douyin"]
    done = 0
    for job in jobs:
        try:
            result = publish_job(job["uid"], platforms=platforms, yes=yes)
            ok = result.get("results", result)
            log(f"  {'✓' if yes else '(演练)'} {job['uid']}: {str(ok)[:120]}")
            done += 1
        except Exception as e:
            log(f"  ✗ {job['uid']}: {str(e)[:100]}", "error")
    log(f"✓ 发布流程完成：{done}/{len(jobs)}", "success")

    if real_engage:
        log("💬 评论区互动（真回复）...")
        try:
            from s6_publish.engage import run as engage_run
            engage_run(demo=not yes)
            log("✓ 互动完成", "success")
        except Exception as e:
            log(f"✗ 互动异常: {str(e)[:100]}", "error")
    return True


STAGE_RUNNERS = {
    "trend": run_stage_trend,
    "copy": run_stage_copy,
    "storyboard": run_stage_storyboard,
    "generate": run_stage_generate,
    "compose": run_stage_compose,
    "publish": run_stage_publish,
}


def run_all(only: list = None, dry: bool = False):
    """运行全流程"""
    stages_to_run = only if only else STAGES
    total = len(stages_to_run)

    # 清空进度文件
    RUN_PROGRESS_FILE.write_text("", encoding="utf-8")

    log(f"🏭 轻便侠·AI视频工厂 启动（{console_mode()} 模式）：{' → '.join(stages_to_run)}")
    update_status(running=True, stage=stages_to_run[0], progress=0, message="启动中")

    for idx, stage in enumerate(stages_to_run):
        progress = int((idx / total) * 100)
        update_status(running=True, stage=stage, progress=progress, message=f"运行 {stage}")

        runner = STAGE_RUNNERS.get(stage)
        if not runner:
            log(f"⚠ 未知阶段: {stage}", "warning")
            continue

        try:
            success = runner(dry=dry)
            if not success:
                log(f"✗ 阶段 {stage} 失败", "error")
                update_status(running=False, stage=stage, progress=progress, message=f"{stage} 失败")
                return False
        except Exception as e:
            tb = traceback.format_exc()
            log(f"✗ 阶段 {stage} 异常: {str(e)[:120]}", "error")
            log(tb[-400:], "error")
            update_status(running=False, stage=stage, progress=progress, message=f"{stage} 异常")
            return False

    log("🎉 全流程完成！", "success")
    update_status(running=False, stage=None, progress=100, message="完成")
    return True


def main():
    parser = argparse.ArgumentParser(description="轻便侠·AI视频工厂 全流程引擎")
    parser.add_argument("--only", type=str, help="只运行指定阶段，逗号分隔")
    parser.add_argument("--dry", action="store_true", help="演练模式（不出片不花钱）")
    parser.add_argument("--mode", type=str, choices=["template", "legacy"],
                        help="强制运行模式（默认读 console.json）")
    args = parser.parse_args()

    if args.mode:
        state = load_console_state()
        state["mode"] = args.mode
        CONSOLE_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

    only = args.only.split(",") if args.only else None

    try:
        success = run_all(only=only, dry=args.dry)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("⚠ 用户中断", "warning")
        update_status(running=False, message="用户中断")
        sys.exit(130)


if __name__ == "__main__":
    main()
