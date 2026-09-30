"""外部工具定位（ffmpeg/ffprobe/yt-dlp）

Phase 1：不再写死本机绝对路径。解析顺序：
  1. settings.paths.<tool>（config/default.yaml 或 AYHMJ_PATHS__FFMPEG）
  2. 环境变量 <TOOL>_PATH / <TOOL>（如 FFMPEG_PATH）
  3. PATH
  4. 少量候选项（仓库 vendor/、Windows 常见安装点）——存在才用，不存在静默跳过
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _candidates(name: str) -> list[Path]:
    """候选位置：只返回"可能"的位置，找不到就跳过，绝不硬失败。"""
    root = _repo_root()
    local = os.environ.get("LOCALAPPDATA", "")
    return [
        root / "vendor" / name / "bin",
        root / "tools" / name / "bin",
        Path(local) / "Microsoft" / "WinGet" / "Links" if local else root,
    ]


def find_executable(name: str, known_paths: list[Path] | None = None) -> str:
    # 1. settings（强类型配置）
    try:
        from .settings import get_settings
        configured = getattr(get_settings().paths, name, "")
        if configured:
            p = Path(configured).expanduser()
            if p.is_file():
                return str(p)
    except Exception:
        pass

    # 2. 环境变量
    for env_key in (f"{name.upper()}_PATH", name.upper()):
        env_path = os.environ.get(env_key)
        if env_path and Path(env_path).is_file():
            return env_path

    # 3. PATH
    found = shutil.which(name)
    if found:
        return found

    # 4. 候选目录
    exe_name = f"{name}.exe" if os.name == "nt" else name
    for base in (known_paths or []) + _candidates(name):
        for candidate in (base / exe_name, base / name):
            if candidate.is_file():
                return str(candidate)

    raise FileNotFoundError(
        f"找不到 {name}：请设置 {name.upper()}_PATH，或写进 config/default.yaml 的 paths.{name}")


def ffmpeg() -> str:
    return find_executable("ffmpeg")


def ffprobe() -> str:
    return find_executable("ffprobe")


def yt_dlp() -> str:
    return find_executable("yt-dlp")


# 常见中文字体文件名片段（用于在本机字体目录里挑一个可用字体）
FONT_HINTS = ("新青年", "青年体", "YaHei", "msyh", "SourceHan", "Noto", "SimHei")


def font_dir() -> Path:
    """字体目录（libass fontsdir / PNG 绘制用）。

    解析顺序：settings.paths.fonts_dir → <root>/assets/fonts → 系统字体目录。
    """
    try:
        from .settings import get_settings
        s = get_settings()
        if s.paths.fonts_dir:
            d = s.resolve(s.paths.fonts_dir)
            if d.is_dir():
                return d
        repo = s.root / "assets" / "fonts"
        if repo.is_dir():
            return repo
    except Exception:
        pass
    system_root = os.environ.get("SYSTEMROOT") or "C:/Windows"
    return Path(system_root) / "Fonts"


def find_font(*, bold: bool = False) -> Path | None:
    """在字体目录里找可用中文字体；找不到返回 None（调用方自行回退）。"""
    d = font_dir()
    if not d.is_dir():
        return None
    try:
        files = [f for f in d.iterdir() if f.suffix.lower() in {".ttf", ".ttc", ".otf"}]
    except OSError:
        return None
    for f in files:
        if bold and any(h.lower() in f.name.lower() for h in ("bold", "bd", "w8", "heavy")):
            return f
    for f in files:
        if any(h.lower() in f.name.lower() for h in FONT_HINTS):
            return f
    return files[0] if files else None


def get_video_duration(video_path: str) -> float:
    """获取视频时长（秒）"""
    cmd = [
        ffprobe(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"ffprobe 失败: {result.stderr[-200:] if result.stderr else video_path}")
    return float(result.stdout.strip())


def get_video_info(video_path: str) -> dict:
    """获取视频信息"""
    cmd = [
        ffprobe(), "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"ffprobe 失败: {result.stderr[-200:] if result.stderr else video_path}")
    return json.loads(result.stdout)
