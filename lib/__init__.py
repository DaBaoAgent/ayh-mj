"""ayh-mj 公共库"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
STATE_DIR = PROJECT_ROOT / "state"
OUT_DIR = PROJECT_ROOT / "out"
LOGS_DIR = PROJECT_ROOT / "logs"
ASSETS_DIR = PROJECT_ROOT / "assets"

# 确保目录存在
for d in [STATE_DIR, OUT_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)
