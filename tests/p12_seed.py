"""Phase 12 前端测试造数入口 —— 在**另一个进程**里按 spec 往同一个 state 目录写任务。

用法：`python tests/p12_seed.py <spec.json>`（需要 AYHMJ_STATE_DIR 与 AYHMJ_OUT_DIR 指向隔离目录）。
这样 Playwright 的 uvicorn 子进程与造数进程看到的是同一份 canonical 事实源。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python tests/p12_seed.py <spec.json>", file=sys.stderr)
        return 2
    spec_path = Path(argv[1]).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    from lib import STATE_DIR
    from lib.jobstore import store
    from tests.p12_support import apply_spec

    uids = [apply_spec(store, STATE_DIR, job) for job in spec.get("jobs", [])]
    print(json.dumps({"state_dir": str(STATE_DIR), "uids": uids}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
