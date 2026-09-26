"""R2 批次串行生成 7 段（新音色 r07 女主版 v3）

用法：
  .venv/Scripts/python.exe tools/run_r2_batch.py
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv/Scripts/python.exe")
LOG = ROOT / "logs/r2_gen.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    log("=" * 50)
    log("R2 批次开始（v3 新音色 r07 女主版）")
    ok, fail = [], []
    for i in range(1, 8):
        uid = f"R2_haoyun_s{i}"
        spec = ROOT / f"state/onetake_prompt_job_{uid}.json"
        log(f"--- 第 {i}/7 段：{uid} ---")
        r = subprocess.run([PY, str(ROOT / "s4_generate/gen_one_take.py"), str(spec)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=str(ROOT))
        for line in (r.stdout or "").strip().splitlines():
            log("  " + line)
        if r.returncode == 0 and (ROOT / f"out/gen_{uid}/onetake.mp4").exists():
            ok.append(uid)
        else:
            fail.append(uid)
            for line in (r.stderr or "").strip().splitlines()[-5:]:
                log("  ERR " + line)
    log(f"完成：成功 {len(ok)} / 失败 {len(fail)}  {fail if fail else ''}")
    log("=" * 50)


if __name__ == "__main__":
    main()
