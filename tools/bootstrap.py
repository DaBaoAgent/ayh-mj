"""一键部署/体检：ayh-mj 换新电脑三步就绪

用法：
    python tools/bootstrap.py --check    # 只体检（= health_check 能力矩阵）
    python tools/bootstrap.py            # 一键补齐 venv + 依赖

Phase 1：体检逻辑统一收敛到 tools/health_check.py，本脚本不再自己维护一份路径/凭据判断。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.console import enable_utf8_console  # noqa: E402
from lib.settings import get_settings  # noqa: E402

enable_utf8_console()

VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"


def check_ffmpeg() -> bool:
    try:
        from lib.tools import ffmpeg, ffprobe
        ffmpeg()
        ffprobe()
        return True
    except FileNotFoundError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="ayh-mj 体检/部署")
    parser.add_argument("--check", action="store_true", help="只体检")
    parser.add_argument("--json", action="store_true", help="JSON 输出（透传 health_check）")
    args = parser.parse_args()

    import json

    from tools.health_check import BLOCKED, format_report, run_health

    report = run_health()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["status"] != BLOCKED else 1
    if args.check:
        print(format_report(report))
        return 0 if report["status"] != BLOCKED else 1

    print("🏥 ayh-mj 体检\n" + "=" * 50)
    print(format_report(report))
    settings = get_settings()
    print(f"   仓库根：{settings.root}")
    print(f"   状态目录：{settings.state_dir}")

    if not VENV_PY.exists():
        print("\n补齐 venv：")
        subprocess.run(["uv", "venv", ".venv"], cwd=str(ROOT), check=False)
        subprocess.run(["uv", "pip", "install", "-r", "requirements.txt"],
                       cwd=str(ROOT), check=False)
        print("✓ venv + 依赖已装，重新运行体检确认")
    return 0 if report["status"] != BLOCKED else 1


if __name__ == "__main__":
    raise SystemExit(main())
