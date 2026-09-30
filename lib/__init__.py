"""ayh-mj 公共库"""
import os
from pathlib import Path

from .console import enable_utf8_console

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
OUT_DIR = PROJECT_ROOT / "out"
LOGS_DIR = PROJECT_ROOT / "logs"
ASSETS_DIR = PROJECT_ROOT / "assets"

# 运行状态目录 / 成片输出目录可用环境变量覆盖（测试隔离 / 多实例并存）。
# 默认仍是仓库内的 state/ 与 out/，不改变任何现有行为。
STATE_DIR = Path(os.environ.get("AYHMJ_STATE_DIR") or (PROJECT_ROOT / "state"))
OUT_DIR = Path(os.environ.get("AYHMJ_OUT_DIR") or OUT_DIR)

# 确保目录存在
for d in [STATE_DIR, OUT_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# CLI 入口的编码兜底：Windows GBK 控制台打印 ✓/emoji 会崩，这里统一开启 UTF-8。
enable_utf8_console()
