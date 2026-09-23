"""全流程引擎 — 唯一执行入口"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import STATE_DIR, LOGS_DIR
from lib.state import create_job, update_job, list_jobs, get_stats

# 状态文件
RUN_STATUS_FILE = STATE_DIR / "run_status.json"
RUN_PROGRESS_FILE = STATE_DIR / "run_progress.jsonl"

# 6 阶段
STAGES = ["trend", "copy", "storyboard", "generate", "compose", "publish"]

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
    print(f"[{level.upper()}] {message}")

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

def run_stage_trend():
    """阶段1: 热点爆款抓取"""
    log("🔥 开始抓取热点爆款...")
    # TODO: 实现抖音热点抓取
    # from s1_trend import douyin_hot
    # trends = douyin_hot.fetch()
    log("✓ 热点抓取完成（演示模式）", "success")
    return True

def run_stage_copy():
    """阶段2: 文案生成"""
    log("📝 开始生成软广文案...")
    # TODO: 实现文案生成
    # from s2_copy import gen_script
    # script = gen_script.generate(trend)
    log("✓ 文案生成完成（演示模式）", "success")
    return True

def run_stage_storyboard():
    """阶段3: 智能分镜"""
    log("🎬 开始智能分镜...")
    # TODO: 实现分镜拆分
    # from s3_storyboard import split
    # shots = split.run(script)
    log("✓ 分镜完成（演示模式）", "success")
    return True

def run_stage_generate():
    """阶段4: H3视频生成"""
    log("🎥 开始 H3 视频生成...")
    # TODO: 实现 AutoDL H3 调用
    # from s4_generate import autodl_client
    # videos = autodl_client.batch_generate(shots)
    log("✓ 视频生成完成（演示模式）", "success")
    return True

def run_stage_compose():
    """阶段5: 合成烧字幕"""
    log("🎞️ 开始合成与烧字幕...")
    # TODO: 实现 TTS + ffmpeg 合成
    # from s5_compose import merge
    # final = merge.run(videos, script)
    log("✓ 合成完成（演示模式）", "success")
    return True

def run_stage_publish():
    """阶段6: 发布互动"""
    log("📤 开始发布（演示模式，不真发）...")
    # TODO: 实现发布
    # from s6_publish import postflow, uploadpost
    log("✓ 发布流程完成（演示模式）", "success")
    return True

STAGE_RUNNERS = {
    "trend": run_stage_trend,
    "copy": run_stage_copy,
    "storyboard": run_stage_storyboard,
    "generate": run_stage_generate,
    "compose": run_stage_compose,
    "publish": run_stage_publish,
}

def run_all(only: list = None):
    """运行全流程"""
    stages_to_run = only if only else STAGES
    total = len(stages_to_run)
    
    log(f"🏭 轻便侠·AI视频工厂 启动")
    log(f"   阶段: {', '.join(stages_to_run)}")
    update_status(running=True, stage=stages_to_run[0], progress=0, message="启动中")
    
    # 清空进度文件
    RUN_PROGRESS_FILE.write_text("", encoding="utf-8")
    
    for idx, stage in enumerate(stages_to_run):
        progress = int((idx / total) * 100)
        update_status(running=True, stage=stage, progress=progress, message=f"运行 {stage}")
        
        runner = STAGE_RUNNERS.get(stage)
        if not runner:
            log(f"⚠ 未知阶段: {stage}", "warning")
            continue
        
        try:
            success = runner()
            if not success:
                log(f"✗ 阶段 {stage} 失败", "error")
                update_status(running=False, stage=stage, progress=progress, message=f"{stage} 失败")
                return False
        except Exception as e:
            log(f"✗ 阶段 {stage} 异常: {e}", "error")
            update_status(running=False, stage=stage, progress=progress, message=f"{stage} 异常")
            return False
    
    log("🎉 全流程完成！")
    update_status(running=False, stage=None, progress=100, message="完成")
    return True

def main():
    parser = argparse.ArgumentParser(description="轻便侠·AI视频工厂 全流程引擎")
    parser.add_argument("--only", type=str, help="只运行指定阶段，逗号分隔")
    parser.add_argument("--dry", action="store_true", help="演练模式")
    args = parser.parse_args()
    
    only = args.only.split(",") if args.only else None
    
    try:
        success = run_all(only=only)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("⚠ 用户中断", "warning")
        update_status(running=False, message="用户中断")
        sys.exit(130)

if __name__ == "__main__":
    main()
