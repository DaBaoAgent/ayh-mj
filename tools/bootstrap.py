"""一键部署/体检：ayh-mj 换新电脑三步就绪

用法：
    python tools/bootstrap.py --check    # 先体检（不动手）
    python tools/bootstrap.py            # 一键补齐
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"


def check_venv() -> tuple[bool, str]:
    """检查虚拟环境"""
    if VENV_PY.exists():
        return True, f"venv 就绪: {VENV_PY}"
    return False, "venv 缺失（运行 uv venv .venv）"


def check_deps() -> tuple[bool, str]:
    """检查依赖"""
    if not VENV_PY.exists():
        return False, "venv 缺失，先建 venv"
    result = subprocess.run(
        [str(VENV_PY), "-c", "import fastapi, httpx, yaml, playwright, edge_tts, PIL; print('ok')"],
        capture_output=True, text=True)
    if "ok" in result.stdout:
        return True, "核心依赖就绪"
    return False, f"依赖缺失: {result.stderr[-200:]}"


def check_ffmpeg() -> tuple[bool, str]:
    """检查 ffmpeg"""
    sys.path.insert(0, str(ROOT))
    try:
        from lib.tools import ffmpeg, ffprobe
        ffmpeg_path = ffmpeg()
        ffprobe()
        return True, f"ffmpeg: {ffmpeg_path}"
    except FileNotFoundError as e:
        return False, str(e)


def check_login() -> tuple[bool, str]:
    """检查抖音登录态（不启动浏览器，只看 profile 目录）"""
    profile = ROOT / "state" / "browser-profile"
    if profile.exists():
        return True, "浏览器 profile 存在（登录态用 python s1_trend/browser.py --check 验证）"
    return False, "浏览器 profile 缺失（运行 python s1_trend/browser.py --login 扫码）"


def check_creds() -> tuple[bool, str]:
    """检查凭据"""
    issues = []
    sys.path.insert(0, str(ROOT))
    try:
        from lib.llm import DEEPSEEK_API_KEY
        if not DEEPSEEK_API_KEY:
            issues.append("DEEPSEEK_API_KEY 缺失（setx DEEPSEEK_API_KEY <key>）")
    except Exception as e:
        issues.append(f"llm 模块异常: {e}")
    try:
        from s4_generate.autodl_client import API_KEY
        if not API_KEY:
            issues.append("AUTODL_API_KEY 缺失（setx AUTODL_API_KEY <key>）")
    except Exception as e:
        issues.append(f"autodl 模块异常: {e}")
    if issues:
        return False, "; ".join(issues)
    return True, "DeepSeek + AutoDL 凭据就绪"


def check_uploadpost() -> tuple[bool, str]:
    """检查 Upload-Post key"""
    try:
        import keyring
        k = keyring.get_password("uploadpost", "api_key")
        if k:
            return True, "Upload-Post key 已存（凭据库）"
    except Exception:
        pass
    if os.environ.get("UPLOADPOST_API_KEY"):
        return True, "Upload-Post key 已存（环境变量）"
    return False, "Upload-Post key 缺失（发布海外才需要，见 README）"


def check_postflow() -> tuple[bool, str]:
    """检查 PostFlow CLI（国内发布依赖）"""
    exe = Path("D:/@kaifa/AutoAYH/pipeline/vendor/postflow/.venv/Scripts/postflow.exe")
    if exe.exists():
        return True, f"PostFlow 就绪: {exe}"
    return False, "PostFlow 缺失（国内发布才需要，从 AutoAYH 仓库部署）"


def main() -> int:
    parser = argparse.ArgumentParser(description="ayh-mj 体检/部署")
    parser.add_argument("--check", action="store_true", help="只体检")
    args = parser.parse_args()

    print("🏥 ayh-mj 体检\n" + "=" * 50)
    checks = [
        ("虚拟环境", check_venv),
        ("核心依赖", check_deps),
        ("ffmpeg", check_ffmpeg),
        ("抖音登录", check_login),
        ("API凭据", check_creds),
        ("Upload-Post", check_uploadpost),
        ("PostFlow", check_postflow),
    ]

    ok_count = 0
    todo_count = 0
    fail_count = 0
    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"检查异常: {str(e)[:100]}"
        icon = "✓" if ok else "○"
        print(f"  {icon} {name}: {msg}")
        if ok:
            ok_count += 1
        else:
            todo_count += 1

    print("=" * 50)
    print(f"{ok_count} 项就绪 · {todo_count} 项待办")

    if not args.check and not VENV_PY.exists():
        print("\n补齐 venv：")
        subprocess.run(["uv", "venv", ".venv"], cwd=str(ROOT))
        subprocess.run(["uv", "pip", "install", "-r", "requirements.txt"], cwd=str(ROOT))
        print("✓ venv + 依赖已装，重新运行体检确认")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
