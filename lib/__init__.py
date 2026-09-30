"""ayh-mj 公共库"""
from pathlib import Path

from .console import enable_utf8_console

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
STATE_DIR = PROJECT_ROOT / "state"
OUT_DIR = PROJECT_ROOT / "out"
LOGS_DIR = PROJECT_ROOT / "logs"
ASSETS_DIR = PROJECT_ROOT / "assets"

# 确保目录存在
for d in [STATE_DIR, OUT_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)

# CLI 入口的编码兜底：Windows GBK 控制台打印 ✓/emoji 会崩，这里统一开启 UTF-8。
enable_utf8_console()
