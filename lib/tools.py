"""外部工具定位（ffmpeg/ffprobe/yt-dlp）"""
import os
import shutil
import subprocess
from pathlib import Path

# 已知安装位置
KNOWN_FFMPEG_PATHS = [
    Path(os.environ.get("FFMPEG_DIR", "")) / "bin",
    Path("D:/@kaifa/tools/ffmpeg/bin"),
    Path("C:/Users/xxx13/ffmpeg/ffmpeg-8.1.1-essentials_build/bin"),
    Path("C:/ffmpeg/bin"),
]

def find_executable(name: str, known_paths: list[Path] = None) -> str:
    """查找可执行文件"""
    # 1. 环境变量
    env_path = os.environ.get(f"{name.upper()}_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. PATH
    found = shutil.which(name)
    if found:
        return found

    # 3. 已知位置
    for p in (known_paths or []):
        exe = p / f"{name}.exe" if os.name == "nt" else p / name
        if exe.exists():
            return str(exe)

    raise FileNotFoundError(f"找不到 {name}，请设置 {name.upper()}_PATH 环境变量或加入 PATH")

def ffmpeg() -> str:
    return find_executable("ffmpeg", KNOWN_FFMPEG_PATHS)

def ffprobe() -> str:
    return find_executable("ffprobe", KNOWN_FFMPEG_PATHS)

def yt_dlp() -> str:
    return find_executable("yt-dlp")

def get_video_duration(video_path: str) -> float:
    """获取视频时长（秒）"""
    cmd = [
        ffprobe(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def get_video_info(video_path: str) -> dict:
    """获取视频信息"""
    import json
    cmd = [
        ffprobe(), "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)
