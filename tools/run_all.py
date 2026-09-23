"""全流程引擎 — 唯一执行入口

阶段选择：s1_trend → s2_copy → s3_storyboard → s4_generate → s5_compose → s6_publish
用法：
    python tools/run_all.py                    # 全流程
    python tools/run_all.py --only trend,copy  # 只跑部分阶段（免费验证用）
    python tools/run_all.py --dry              # 演练（不出片不花钱）
"""
import argparse
import json
import sys
import traceback
from pathlib import Path
from datetime import datetime

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import STATE_DIR
from lib.state import list_jobs, get_stats

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
    return {"daily_target": 3, "real_publish": False, "real_engage": False}


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


def run_stage_storyboard(dry: bool = False):
    """阶段3: 智能分镜"""
    log("🎬 智能分镜...")
    from s3_storyboard.split import run as sb_run
    target = load_console_state().get("daily_target", 3)
    result = sb_run(top=target)
    log(f"✓ 分镜完成：{result.get('processed', 0)} 个任务", "success")
    return True


def run_stage_generate(dry: bool = False):
    """阶段4: H3视频生成"""
    log(f"🎥 H3 视频生成{'（演练）' if dry else ''}...")
    from s4_generate.batch_gen import run as gen_run
    target = load_console_state().get("daily_target", 3)
    result = gen_run(top=target, dry=dry)
    log(f"✓ 生成完成：{result.get('processed', 0)} 个任务", "success")
    return True


def run_stage_compose(dry: bool = False):
    """阶段5: 合成烧字幕"""
    log("🎞️ 合成装配（TTS + 拼接 + 烧字幕）...")
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
    log(f"📤 发布{'（真发）' if real and not dry else '（演练）'}...")
    # TODO: 接入 PostFlow + Upload-Post
    log("⚠ 发布模块开发中（s6_publish 待实现）", "warning")
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

    log(f"🏭 轻便侠·AI视频工厂 启动：{' → '.join(stages_to_run)}")
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
    args = parser.parse_args()

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
