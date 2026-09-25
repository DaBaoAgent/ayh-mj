"""全流程引擎 — 唯一执行入口（模板链路）

热点采集 → 创意知识库预检 → 逐条研究与模板改编 → 出片 → 烧字幕 → 发布

用法：
    python tools/run_all.py                    # 全流程
    python tools/run_all.py --only trend,copy  # 只跑部分阶段（免费验证用）
    python tools/run_all.py --dry              # 演练（不出片不花钱）
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
        state = json.loads(CONSOLE_STATE_FILE.read_text(encoding="utf-8"))
        state.pop("mode", None)
        return state
    return {"daily_target": 1, "real_publish": False, "real_engage": False}


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
    line = f"[{level.upper()}] {message}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(line.encode(encoding, errors="replace").decode(encoding), flush=True)


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
    """阶段2: 模板创作前置的热点/爆款/短剧/对标知识库预检。"""
    log("📝 创意策划：核对热点、爆款、短剧与对标知识库...")
    from lib.creative_research import research_inventory
    inventory = research_inventory()
    if inventory["missing"]:
        raise RuntimeError("创意知识库缺失：" + "、".join(inventory["missing"]))
    log(f"✓ 知识库就绪：热点 {inventory['trends']} / 爆款桥段 {inventory['bridges']} / "
        f"对标 {inventory['benchmarks']} / 短剧规则 {inventory['drama_chars']} 字", "success")
    return True


def run_stage_storyboard(dry: bool = False):
    """阶段3: 每条作品独立研究、选新模板、质检对白并落标准分镜。"""
    target = load_console_state().get("daily_target", 3)
    log("🎬 模板分镜：逐条挖掘知识库、设计新钩子与对白...")
    from lib.creative_research import build_research_brief
    from s3_storyboard.templates import adapt_lines, mark_used, pick_template, to_storyboard

    selected_hotspots: set[str] = set()
    done = 0
    for _ in range(max(1, target)):
        brief = build_research_brief(exclude_titles=selected_hotspots)
        hot_title = brief["hotspot"]["title"]
        selected_hotspots.add(hot_title)
        log(f"  研究选题：{hot_title[:40]}；爆款 {len(brief['viral_examples'])} / "
            f"短剧 {len(brief['short_drama_patterns'])} / 对标 {len(brief['benchmark_patterns'])}")
        tpl = pick_template()
        if dry:
            log(f"  (演练) 选用 {tpl['id']} {tpl['name']}；不调用模型、不写任务、不出片")
            done += 1
            continue
        lines_result = adapt_lines(tpl, hot_title, research_brief=brief)
        uid = create_job(trend_id=brief["hotspot"].get("id"))
        sb = to_storyboard(tpl, lines_result["lines"], job_uid=uid)
        sb["hot_title"] = hot_title
        sb["creative_research"] = brief
        sb["creative_design"] = lines_result["creative_design"]
        tw = lines_result.get("scene_tweaks") or {}
        for shot in sb["shots"]:
            tweak = tw.get(str(shot["seq"]))
            if isinstance(tweak, dict):
                for field in ("start_state", "end_state"):
                    if tweak.get(field):
                        shot[field] = tweak[field]
        from lib.cast import _role_group_for
        rg = _role_group_for(uid)
        sb["role_group"] = rg["name"]
        sb["role_group_cast"] = {k: v for k, v in rg.items() if k != "name" and v}
        sp = lines_result.get("sales_point")
        if sp:
            from lib.products import record_point
            record_point(sp["id"], uid)
            sb["sales_point"] = sp
        ang = lines_result.get("angle")
        if ang:
            from lib.angles import record_angle
            record_angle(ang["id"], uid)
            sb["angle"] = ang
        sb_path = STATE_DIR / f"storyboard_{uid}.json"
        sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
        update_job(uid, status="storyboard", storyboard=json.dumps(sb, ensure_ascii=False))
        mark_used(tpl["id"])
        from lib.ideas import record_idea
        record_idea(tpl["id"], tpl["name"], hot_title,
                    lines_result["lines"], lines_result["creative_design"]["novelty"])
        log(f"  ✓ {uid}: {tpl['id']} {tpl['name']}（{lines_result.get('reason', '')[:30]}）")
        done += 1
    log(f"✓ 分镜完成：{done} 个任务", "success")
    return True


def run_stage_generate(dry: bool = False):
    """阶段4: H3视频生成"""
    target = load_console_state().get("daily_target", 3)
    log(f"🎥 模板链路出片（选角+音色克隆）{'（演练）' if dry else ''}...")
    from s4_generate.gen_from_storyboard import run as gen_run
    jobs = list_jobs("storyboard", limit=target)
    if not jobs:
        log("⚠ 没有待生成任务（status=storyboard）", "warning")
        return True
    concurrency = int(load_console_state().get("gen_concurrency", 6))
    done = 0
    for job in jobs:
        sb_path = STATE_DIR / f"storyboard_{job['uid']}.json"
        if not sb_path.exists():
            log(f"  ⚠ {job['uid']}: 缺分镜文件，跳过", "warning")
            continue
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
        if not sb.get("template_id") or not sb.get("creative_research") or not sb.get("creative_design"):
            log(f"  ⚠ {job['uid']}: 不是经过创意研究的模板分镜，禁止出片", "warning")
            continue
        if dry:
            log(f"  (演练) {job['uid']}")
            continue
        try:
            final = gen_run(str(sb_path), concurrency=concurrency)
            update_job(job["uid"], status="generate", video_path=str(final))
            log(f"  ✓ {job['uid']}: {final.name}", "success")
            done += 1
        except Exception as e:
            log(f"  ✗ {job['uid']}: {str(e)[:100]}", "error")
    log(f"✓ 生成完成：{done}/{len(jobs)}", "success")
    return True


def run_stage_compose(dry: bool = False):
    """阶段5: 合成烧字幕"""
    log("🎞️ 模板链路烧字幕...")
    from s5_compose.burn_subtitles import burn
    jobs = list_jobs("generate", limit=10)
    if not jobs:
        log("⚠ 没有待装配任务", "warning")
        return True

    done = 0
    for job in jobs:
        sb_path = STATE_DIR / f"storyboard_{job['uid']}.json"
        if not sb_path.exists() or not json.loads(sb_path.read_text(encoding="utf-8")).get("template_id"):
            log(f"  ⚠ {job['uid']}: 非模板分镜，跳过装配", "warning")
            continue
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
        sb_path = STATE_DIR / f"storyboard_{job['uid']}.json"
        if not sb_path.exists() or not json.loads(sb_path.read_text(encoding="utf-8")).get("template_id"):
            log(f"  ⚠ {job['uid']}: 非模板作品，跳过发布", "warning")
            continue
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

    log(f"🏭 爱优护AI视频工厂 启动（模板链路）：{' → '.join(stages_to_run)}")
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
    parser = argparse.ArgumentParser(description="爱优护AI视频工厂 模板链路引擎")
    parser.add_argument("--only", type=str, help="只运行指定阶段，逗号分隔")
    parser.add_argument("--dry", action="store_true", help="演练模式（不出片不花钱）")
    args = parser.parse_args()

    only = args.only.split(",") if args.only else None

    # 演练模式：CLI --dry 或控制台设置 dry_mode
    dry = args.dry or bool(load_console_state().get("dry_mode"))

    try:
        success = run_all(only=only, dry=dry)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("⚠ 用户中断", "warning")
        update_status(running=False, message="用户中断")
        sys.exit(130)


if __name__ == "__main__":
    main()
