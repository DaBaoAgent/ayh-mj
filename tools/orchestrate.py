"""统一生产 CLI（Phase 3）—— WebUI / Hermes / 命令行共用同一个 Orchestrator。

用法
  python tools/orchestrate.py start  [--goal 选题] [--count N] [--spec X.json] [--dry] [--force]
  python tools/orchestrate.py status [--uid U]
  python tools/orchestrate.py resume --uid U
  python tools/orchestrate.py retry  --uid U
  python tools/orchestrate.py cancel [--uid U | --all]
  python tools/orchestrate.py recover            # 重启后收敛遗留"运行中"任务 → PAUSED

说明
  · start 默认阻塞到全部任务跑完（CLI 语义）；WebUI 走同一个 start，但 background=True；
  · 设置以 state/console.json（WebUI 设置面板）为基准，--count/--dry 可覆盖；
  · 任何失败都会写进 JobStore 的 attempts/events，并回传非零退出码。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.jobstore import JobState, store  # noqa: E402
from lib.orchestrator import orchestrator, start_production  # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_start(args) -> int:
    result = start_production(
        goal=args.goal, count=args.count, dry=True if args.dry else None, source="cli",
        force=args.force, specs=[args.spec] if args.spec else None, background=False)
    if not result.get("ok"):
        print("✗ " + str(result.get("error")))
        return 1
    print(f"▶ {result['message']}")
    failed = []
    for uid in result["jobs"]:
        job = store.get_job(uid) or {}
        mark = "✅" if job.get("status") == JobState.READY else "❌"
        print(f"  {mark} {uid} → {job.get('status')} {job.get('error_code') or ''}")
        if job.get("status") != JobState.READY:
            failed.append(uid)
    print(f"完成：成功 {len(result['jobs']) - len(failed)} / 失败 {len(failed)}")
    return 1 if failed else 0


def cmd_status(args) -> int:
    if args.uid:
        detail = store.detail(args.uid)
        if not detail:
            _print({"error": f"任务不存在：{args.uid}"})
            return 1
        _print({"orchestrator": orchestrator.status(), **detail})
        return 0
    _print({"orchestrator": orchestrator.status(), "counts": store.counts()})
    return 0


def cmd_resume(args) -> int:
    result = orchestrator.resume(args.uid, background=False)
    _print(result)
    return 0 if result.get("ok") else 1


def cmd_retry(args) -> int:
    result = orchestrator.retry(args.uid, background=False)
    _print(result)
    return 0 if result.get("ok") else 1


def cmd_cancel(args) -> int:
    result = orchestrator.cancel(args.uid, all=args.all, reason="CLI 取消")
    _print(result)
    return 0 if result.get("ok") else 1


def cmd_recover(_args) -> int:
    recovered = orchestrator.recover_interrupted()
    _print({"recovered": recovered, "count": len(recovered)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="orchestrate", description="ayh-mj 统一生产编排入口")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="创建并执行 daily_target 条任务（阻塞）")
    s.add_argument("--goal", default="", help="选题/目标（队列为空时用它创建任务）")
    s.add_argument("--count", type=int, default=None, help="覆盖 daily_target")
    s.add_argument("--spec", default="", help="只跑指定的 spec 文件")
    s.add_argument("--dry", action="store_true", help="演练：不出片、不花钱、不发布")
    s.add_argument("--force", action="store_true", help="跳过门禁自检")
    s.set_defaults(func=cmd_start)

    st = sub.add_parser("status", help="查看编排器与任务状态")
    st.add_argument("--uid", default="", help="查看单个任务完整 trace")
    st.set_defaults(func=cmd_status)

    r = sub.add_parser("resume", help="从断点继续任务")
    r.add_argument("--uid", required=True)
    r.set_defaults(func=cmd_resume)

    t = sub.add_parser("retry", help="重试 FAILED/BLOCKED 任务")
    t.add_argument("--uid", required=True)
    t.set_defaults(func=cmd_retry)

    c = sub.add_parser("cancel", help="协作式取消（无孤儿子进程）")
    c.add_argument("--uid", default="")
    c.add_argument("--all", action="store_true")
    c.set_defaults(func=cmd_cancel)

    rc = sub.add_parser("recover", help="重启后把遗留运行中任务收敛为 PAUSED")
    rc.set_defaults(func=cmd_recover)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
