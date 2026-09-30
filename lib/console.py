"""控制台编码兜底：Windows 默认 GBK 控制台无法打印 ✓ / emoji，会让自检脚本直接崩。

Phase 0 记录为基线缺陷（bootstrap / engage --demo 在 GBK 控制台下 UnicodeEncodeError）。
这里提供统一的开启函数，所有 CLI 入口调用它即可，不再各自 `sys.stdout.reconfigure`。
"""
from __future__ import annotations

import contextlib
import sys


def enable_utf8_console() -> None:
    """尽力把 stdout/stderr 切到 UTF-8；不支持的流（如已被重定向的）静默跳过。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError, AttributeError):
            reconfigure(encoding="utf-8", errors="replace")
