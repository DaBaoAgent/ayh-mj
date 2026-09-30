"""s7_learn CLI —— 导入表现快照 / 生成复盘报告。

    python -m s7_learn.run import <fixture.json>     # 幂等导入表现快照
    python -m s7_learn.run report [--day 2026-09-30] # 跑学习闭环 + 写复盘
    python -m s7_learn.run show  [--day ...]         # 只打印一行摘要

默认 **不联网、不写平台**：所有数据来自本地 `performance_metrics` 或显式传入的 fixture。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.console import enable_utf8_console  # noqa: E402
from lib.jobstore import store  # noqa: E402
from lib.settings import get_settings  # noqa: E402
from s7_learn import pipeline, summary_of  # noqa: E402

enable_utf8_console()


def _learn_kwargs() -> dict:
    learn_cfg = get_settings().learn
    return {"window_days": learn_cfg.window_days, "prior_n": learn_cfg.prior_n,
            "min_medium": learn_cfg.min_samples_medium,
            "min_high": learn_cfg.min_samples_high}


def cmd_import(args) -> int:
    result = pipeline.import_fixture(ROOT, store, args.path, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if not result["errors"] else 2


def cmd_report(args) -> int:
    summary = pipeline.learn_from_store(ROOT, store, day=args.day, write=True, **_learn_kwargs())
    print(f"📊 {summary_of(summary)}")
    print(f"   报告：{summary['paths']['markdown']}")
    return 0


def cmd_show(args) -> int:
    summary = pipeline.learn_from_store(ROOT, store, day=args.day, write=False, **_learn_kwargs())
    print(f"📊 {summary_of(summary)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="表现学习层（Phase 11）")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="导入表现快照 fixture（幂等）")
    imp.add_argument("path")
    imp.add_argument("--dry-run", action="store_true")
    imp.set_defaults(func=cmd_import)

    rep = sub.add_parser("report", help="跑学习闭环并写复盘报告")
    rep.add_argument("--day", default="")
    rep.set_defaults(func=cmd_report)

    show = sub.add_parser("show", help="只打印复盘摘要，不落盘")
    show.add_argument("--day", default="")
    show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
