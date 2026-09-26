"""断线接续下载：提交后网络中断（Errno 10053 等）时，别重提交（重复扣钱），用 task_id 接住结果

背景（2026-09-26 实测）：AutoDL 任务已 SUCCESS，但本地下载时撞上连接中断，gen_one_take 报
「全部工作流失败」——重提交会再花一次钱。正确做法：查 task_id 状态 → SUCCESS 就直接拉结果 URL。

用法：
  .venv/Scripts/python.exe tools/resume_task.py <task_id> <输出路径>
  # task_id 可从 out/gen_<uid>/onetake_result.json 或 gen.log 里读到
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("用法：resume_task.py <task_id> <输出路径>")
    tid, out = sys.argv[1], Path(sys.argv[2])
    if not out.is_absolute():
        out = ROOT / out

    import httpx
    from s4_generate.autodl_client import query_task

    r = query_task(tid)
    st = r.get("status")
    print(f"task {tid} → {st}（duration {r.get('duration')}s）")
    if st != "SUCCESS":
        raise SystemExit(f"✗ 任务状态 {st}，无需下载（RUNNING 可稍后重试）")
    res = r.get("results") or []
    if not res:
        raise SystemExit("✗ 结果里没有 URL")
    url = (res[0].get("url") if isinstance(res[0], dict) else str(res[0])).strip()
    out.parent.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(timeout=300, trust_env=False)     # trust_env=False：避免代理干扰
    with c.stream("GET", url) as resp:
        resp.raise_for_status()
        with out.open("wb") as f:
            for chunk in resp.iter_bytes(1 << 20):
                f.write(chunk)
    print(f"✓ 已下载 {out}  {out.stat().st_size / 1e6:.1f}MB")
    # 顺手补齐 result 快照，便于后续脚本识别
    snap = out.parent / "onetake_result.json"
    if not snap.exists():
        snap.write_text(json.dumps({"task_id": tid, "workflow": r.get("workflow", "resumed"),
                                    "video_path": str(out), "duration": r.get("duration", 0),
                                    "resumed": True}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
