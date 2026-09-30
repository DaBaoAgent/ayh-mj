"""15 秒软广管线 · 旧入口（Phase 3 降级为 CLI adapter，Phase 14 标记 DEPRECATED）。

⚠️ 2026-09-30（Phase 3）：**核心编排已统一到 `lib/orchestrator`**。
   本脚本不再承担任何业务编排（不再自己扫队列、不再自己推状态、不再自己写
   run_status.json）——它只把老参数翻译成新 CLI 的参数，保证控制台、老脚本、
   文档里出现的 `tools/run_all.py ...` 继续可用。

   生产执行请直接看 `tools/orchestrate.py`（WebUI 的「启动生产」走的是同一个
   `PipelineOrchestrator`，三条入口的 DB 结构完全一致）。

参数映射
   tools/run_all.py --dry            → tools/orchestrate.py start --dry
   tools/run_all.py --force          → tools/orchestrate.py start --force
   tools/run_all.py --only generate  → 忽略（现行管线无阶段切分，仅提示）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.orchestrate import main as orchestrate_main  # noqa: E402


def _translate(argv: list[str]) -> list[str]:
    out: list[str] = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--only":
            print("提示：--only 已废弃（现行管线无阶段切分），忽略该参数")
            skip_next = True
            continue
        if arg.startswith("--only="):
            print("提示：--only 已废弃（现行管线无阶段切分），忽略该参数")
            continue
        out.append(arg)
    return out


def main(argv: list[str] | None = None) -> int:
    print("[deprecated] tools/run_all.py 是旧入口（只做参数翻译）。"
          "生产请直接用 tools/orchestrate.py，或走 WebUI「启动生产」。", file=sys.stderr)
    raw = list(sys.argv[1:] if argv is None else argv)
    return orchestrate_main(["start", *_translate(raw)])


if __name__ == "__main__":
    raise SystemExit(main())
