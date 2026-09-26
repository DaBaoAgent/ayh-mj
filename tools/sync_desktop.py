"""成片自动同步到桌面 — 宝哥令（2026-09-25）

out/approved/ 的成片 + 分镜元数据 → C:/Users/xxx13/Desktop/ayh-mj/
规则：只复制「新增 / 更新」的文件（按大小+时间戳判定），幂等、可重复跑。

用法：
  .venv/Scripts/python.exe tools/sync_desktop.py          # 有变化时打印摘要
  .venv/Scripts/python.exe tools/sync_desktop.py --quiet  # 无变化时零输出（cron 用）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "approved"
DST = Path("C:/Users/xxx13/Desktop/ayh-mj")
PATTERNS = ("*.mp4", "*.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="无变化时零输出（watchdog 模式）")
    args = ap.parse_args()

    DST.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for pat in PATTERNS:
        for f in sorted(SRC.glob(pat)):
            t = DST / f.name
            if (not t.exists()
                    or t.stat().st_size != f.stat().st_size
                    or t.stat().st_mtime < f.stat().st_mtime - 1):
                shutil.copy2(f, t)
                copied.append(f.name)

    if copied:
        print(f"[桌面同步] 复制 {len(copied)} 个文件 → {DST}")
        for n in copied:
            print(f"  + {n}")
    elif not args.quiet:
        total = len(list(DST.iterdir()))
        print(f"[桌面同步] 无新文件（桌面目录共 {total} 项）")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # cron 下任何异常都要显式可见
        print(f"[桌面同步] 失败: {e}", file=sys.stderr)
        sys.exit(1)
