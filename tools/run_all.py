"""15 秒软广管线 · 总入口（前端控制台「启动生产」调这里）

⚠️ 2026-09-26 重建说明
  老模板全流程（trend→copy→storyboard→generate→compose→publish 的逐阶段脚本链路）已清退，
  代码在 `_deprecated_20260925/`，执行标准见 `docs/执行标准-20260925.md`。
  现行管线 = **15 秒 one-take 单条出片**，一条命令走完：
    四池选角 → spec → check_dialogue 门禁（0 ERROR）→ H3 生成 15s/768p
    → 明快档裁剪 → 字级字幕 → 烧字幕 → BGM + 4 音效 → 抽帧验收 → 归档 out/approved/ + 桌面同步
  入口脚本：`tools/make_15s.py`（详见 `docs/15秒软广-产线说明.md`）

本脚本的职责 = **队列执行器**，让控制台按钮仍然可用：
  1. 把待出的 spec 丢进 `state/queue_15s/`（每个 `*.json` 一条，结构与 state/onetake_prompt_job_<uid>.json 相同）
  2. 控制台点「启动生产」（POST /api/start）→ 本脚本按文件名顺序逐条跑 `make_15s.py run`
  3. 进度实时写 `state/run_status.json`（前端顶部进度条）与 `state/run_progress.jsonl`（历史）
  4. 跑完的 spec 移入 `state/queue_15s/_done/`，不会重复出片

用法
  .venv/Scripts/python.exe tools/run_all.py            # 跑完整个队列
  .venv/Scripts/python.exe tools/run_all.py --dry      # 演练（不花钱，不出片）
  .venv/Scripts/python.exe tools/run_all.py --only generate   # 兼容前端老参数（阶段名已无意义，仅提示）
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
QUEUE = STATE / "queue_15s"
DONE = QUEUE / "_done"
STATUS = STATE / "run_status.json"
PROGRESS = STATE / "run_progress.jsonl"
LOGDIR = STATE / "logs"
MAKE_15S = ROOT / "tools" / "make_15s.py"
PY = str(ROOT / ".venv/Scripts/python.exe") if (ROOT / ".venv/Scripts/python.exe").exists() else sys.executable

# 前端进度条把这 6 个 id 当阶段序列（webui/static/app.js），出片过程中停在 generate→compose
STAGE_GENERATE = "generate"
STAGE_COMPOSE = "compose"


def write_status(**kw) -> None:
    cur = {}
    if STATUS.exists():
        try:
            cur = json.loads(STATUS.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    cur.update(kw)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")


def log_line(msg: str) -> None:
    print(msg, flush=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    f = LOGDIR / f"pipeline_{time.strftime('%Y%m%d')}.log"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def append_progress(rec: dict) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="15 秒软广管线队列调度")
    ap.add_argument("--only", default="", help="（兼容旧参数，已无阶段语义）")
    ap.add_argument("--dry", action="store_true", help="演练：只打印将执行的动作，不花钱不出片")
    ap.add_argument("--force", action="store_true", help="跳过门禁/字数自检（传给 make_15s）")
    args = ap.parse_args()

    QUEUE.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    specs = sorted(p for p in QUEUE.glob("*.json") if p.is_file())

    if args.only:
        log_line(f"提示：已收到旧参数 --only {args.only}；现行管线无阶段切分，忽略该参数")

    if not specs:
        msg = ("队列为空：把 spec 放进 state/queue_15s/ 再点启动；"
               "或直接跑 .venv/Scripts/python.exe tools/make_15s.py run state/onetake_prompt_job_<uid>.json")
        log_line("• " + msg)
        write_status(running=False, current_stage=None, progress=0, message=msg,
                     started_at=None, finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        return 0

    total = len(specs)
    log_line(f"▶ 15s 管线队列启动：{total} 条 ｜ python={PY}")
    write_status(running=True, current_stage=STAGE_GENERATE, progress=0,
                 message=f"出片队列启动（0/{total}）", started_at=time.strftime("%Y-%m-%d %H:%M:%S"))

    ok = fail = 0
    for i, spec in enumerate(specs, start=1):
        uid = spec.stem
        pct = int((i - 1) / total * 100)
        write_status(running=True, current_stage=STAGE_GENERATE, progress=pct,
                     message=f"出片 {uid}（{i}/{total}）")
        t0 = time.time()
        cmd = [PY, str(MAKE_15S), "run", str(spec)]
        if args.dry:
            cmd.append("--dry")
        if args.force:
            cmd.append("--force")
        log_line(f"  ▷ {uid}：{' '.join(cmd[1:])}")
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, errors="replace")
        el = time.time() - t0
        out = (r.stdout or "") + (r.stderr or "")
        tail = "\n".join(out.strip().splitlines()[-15:])
        success = (r.returncode == 0) and (
            args.dry or f"{uid}_" in out or "🎬 成片" in out or "归档" in out)
        if success:
            ok += 1
            log_line(f"  ✅ {uid} 完成（{el / 60:.1f} 分钟）")
            if not args.dry:
                shutil.move(str(spec), str(DONE / spec.name))
        else:
            fail += 1
            log_line(f"  ❌ {uid} 失败（{el / 60:.1f} 分钟）\n{tail}")
        append_progress({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "uid": uid, "ok": success,
            "minutes": round(el / 60, 1), "returncode": r.returncode,
            "tail": tail[-400:],
        })
        write_status(running=True, current_stage=STAGE_COMPOSE, progress=int(i / total * 100),
                     message=f"{'完成' if success else '失败'} {uid}（{i}/{total}）")

    msg = f"队列完成：成功 {ok} / 失败 {fail}（共 {total} 条）" + ("（演练模式）" if args.dry else "")
    log_line("✔ " + msg)
    write_status(running=False, current_stage=None, progress=100, message=msg,
                 finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
