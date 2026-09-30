#!/usr/bin/env python3
"""ayh-mj CI 门禁（Phase 13）—— 一条命令跑完所有非 live / 非 paid 测试。

顺序与计划 §Phase 13「CI 门禁」一致：

    lint、typecheck、markers、unit、contract、integration、frontend smoke、migration

规则：
  · 任一步非零退出立即停手（PR 未全绿禁止合并）；
  · **强制清除** AYHMJ_RUN_LIVE / AYHMJ_RUN_PAID —— CI 永不跑 live，永不提交付费
    任务，永不真实发布（这是硬约束，不是"默认值"）；
  · typecheck 在本仓 = 编译期语法检查（`compileall`）。仓库没有 mypy，本阶段也
    不引入新依赖，所以用"能不能编译"当类型/语法闸门；
  · markers 步是**分类纪律**：tests/unit 下每条用例都必须带 `unit` marker。
    新增测试忘了打 marker 会让它悄悄逃出门禁，这里直接把这种逃逸变成红灯。

用法：
    .venv/Scripts/python.exe tools/ci.py                  # 跑全部
    .venv/Scripts/python.exe tools/ci.py --skip-frontend  # 无浏览器环境
    .venv/Scripts/python.exe tools/ci.py --list           # 只打印步骤
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# 需要 compileall 的包（有 .py 的全部生产/测试目录）
TYPECHECK_TARGETS = [
    "lib", "s1_trend", "s2_copy", "s3_storyboard", "s4_generate", "s5_compose",
    "s6_publish", "s7_learn", "tools", "webui", "tests",
]

# 目录 与 该目录唯一允许的 marker（分类纪律）
MARKER_DIRS = [
    ("tests/unit", "unit"),
    ("tests/contract", "contract"),
    ("tests/integration", "integration"),
    ("tests/frontend", "frontend"),
]

PYTEST = [PY, "-m", "pytest"]
LINT_TARGETS = ["lib", "tests", "tools", "webui", "s6_publish", "s7_learn"]


def _steps(skip_frontend: bool) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = [
        ("lint", [PY, "-m", "ruff", "check", *LINT_TARGETS]),
        ("typecheck", [PY, "-m", "compileall", "-q", *TYPECHECK_TARGETS]),
        ("unit", [*PYTEST, "tests/unit", "-q", "--timeout=900"]),
        ("contract", [*PYTEST, "tests/contract", "-q", "--timeout=900"]),
        ("integration", [*PYTEST, "tests/integration", "-q", "--timeout=900"]),
    ]
    if not skip_frontend:
        steps.append(("frontend", [*PYTEST, "tests/frontend", "-q", "--timeout=900"]))
    steps.append(("migration", [*PYTEST, "tests/unit/test_migrations.py", "-q", "--timeout=900"]))
    return steps


def _child_env() -> dict:
    """CI 子进程环境：绝不继承 live/paid 开关，输出强制 UTF-8。"""
    env = dict(os.environ)
    for key in ("AYHMJ_RUN_LIVE", "AYHMJ_RUN_PAID"):
        env.pop(key, None)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(argv: list[str]) -> int:
    print("    $ " + " ".join(argv), flush=True)
    t0 = time.time()
    proc = subprocess.run(argv, cwd=str(ROOT), env=_child_env())  # noqa: S603
    print(f"    ({time.time() - t0:.1f}s, exit={proc.returncode})", flush=True)
    return proc.returncode


def _marker_hygiene() -> int:
    """每个测试目录下不允许出现"没打对应 marker"的用例（那会让它逃出门禁）。"""
    bad: list[str] = []
    for rel, marker in MARKER_DIRS:
        out = subprocess.run(  # noqa: S603
            [*PYTEST, rel, "-m", f"not {marker}", "--collect-only", "-q",
             "-p", "no:cacheprovider"],
            cwd=str(ROOT), env=_child_env(), capture_output=True, text=True, errors="replace")
        text = (out.stdout or "") + (out.stderr or "")
        if "no tests collected" in text:
            print(f"    ok {rel}: 全部用例都带 {marker} marker")
            continue
        match = re.search(r"(\d+) tests? collected", text)
        count = match.group(1) if match else "?"
        bad.append(f"{rel} 有 {count} 条用例没带 {marker} marker")
    if bad:
        for line in bad:
            print("    FAIL " + line)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ayh-mj CI 门禁（非 live 全量）")
    ap.add_argument("--skip-frontend", action="store_true", help="跳过 Playwright（无浏览器环境）")
    ap.add_argument("--list", action="store_true", help="只打印步骤名")
    args = ap.parse_args()

    steps = _steps(args.skip_frontend)
    if args.list:
        for name, argv in steps:
            print(f"{name}: {' '.join(argv)}")
        return 0

    print("=" * 68)
    print("ayh-mj CI 门禁（非 live / 非 paid，live 与 paid 环境变量已强制清除）")
    print("=" * 68)

    started = time.time()
    results: list[tuple[str, int, float]] = []
    for name, argv in steps:
        print(f"\n>>> {name}")
        t0 = time.time()
        code = _run(argv)
        if code == 0 and name == "unit":
            # unit 步之后顺带做一次分类纪律检查（每一步都要真的跑，不能互相顶替）
            code = _marker_hygiene()
        results.append((name, code, time.time() - t0))
        if code != 0:
            print(f"\n!! 步骤 {name} 失败（exit={code}），后续步骤不再执行")
            break

    print("\n" + "=" * 68)
    print("汇总")
    print("=" * 68)
    for name, code, seconds in results:
        print(f"  {'PASS' if code == 0 else 'FAIL'}  {name:<12} {seconds:6.1f}s")
    total = time.time() - started
    failed = [name for name, code, _ in results if code != 0]
    if failed:
        print(f"\n门禁未通过：{', '.join(failed)}（总耗时 {total:.1f}s）")
        return 1
    print(f"\n全部门禁通过（总耗时 {total:.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
