"""短剧狗血10连·对抗加码版 — 批量提交 + 轮询下载

用法：
  .venv/Scripts/python.exe tools/run_batch_duikang10.py --submit    # 提交全部（10 条）
  .venv/Scripts/python.exe tools/run_batch_duikang10.py --collect   # 轮询并下载全部完成的

结构同 run_batch_brain2.py（B2 脑洞10连已验证）；uid 列表取自 tools/prep_duikang10.py。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from s4_generate import autodl_client as ac  # noqa: E402
from prep_duikang10 import SCRIPTS  # noqa: E402

BATCH_FILE = ROOT / "state/batch_duikang10_jobs.json"
UIDS = [s["uid"] for s in SCRIPTS]


def selected() -> list[str]:
    """只处理命令行指定的 uid（无参数=全批）"""
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    return only if only else UIDS


def build_payload(spec: dict) -> dict:
    payload: dict = {
        "prompt": spec["prompt"],
        "duration": int(spec["duration"]),
        "resolution": spec["resolution"],
    }
    for i, img in enumerate(spec["ref_images"][:9]):
        p = ROOT / img if not Path(img).is_absolute() else Path(img)
        payload[f"ref_image_{i}"] = ac.to_data_url(str(p))
    for i, a in enumerate(spec["ref_audios"][:3]):
        p = ROOT / a if not Path(a).is_absolute() else Path(a)
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(p), resize=False)
    return payload


def submit(force: bool = False) -> None:
    jobs = []
    if BATCH_FILE.exists():
        jobs = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    todo = selected()
    if force:
        # 重跑模式：清掉待跑条目的旧记录，允许重新提交
        jobs = [j for j in jobs if j["uid"] not in todo]
        print(f"  [重跑模式] 已清空 {len(todo)} 条旧记录")
    have = {j["uid"] for j in jobs}
    failed = 0
    for uid in todo:
        if uid in have:
            print(f"  跳过（已提交）: {uid}")
            continue
        spec_path = ROOT / f"state/onetake_prompt_job_{uid}.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        print(f"🧩 提交 {uid} ...", flush=True)
        try:
            tid = ac.create_task(spec["workflow"], build_payload(spec))
        except Exception as e:
            failed += 1
            print(f"  ❌ 提交失败: {str(e)[:200]}", flush=True)
            if failed >= 2:
                print("连续失败，中止（避免重复扣费/刷错误）"); break
            continue
        jobs.append({"uid": uid, "task_id": tid, "status": "RUNNING",
                     "title": uid, "out": f"out/gen_job_{uid}/onetake.mp4"})
        BATCH_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  ✓ {uid} → {tid}", flush=True)
    print(f"\n已提交 {len(jobs)}/{len(todo)}")


def collect() -> None:
    if not BATCH_FILE.exists():
        print("还没有批量记录，先 --submit"); return
    jobs = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    todo = selected()
    jobs = [j for j in jobs if j["uid"] in todo]
    for rnd in range(400):
        pending = [j for j in jobs if j["status"] not in ("DONE", "FAILED")]
        if not pending:
            print("✅ 全部结束"); break
        print(f"--- 第 {rnd + 1} 轮（待 {len(pending)}）---", flush=True)
        for j in jobs:
            if j["status"] in ("DONE", "FAILED"):
                continue
            try:
                st = ac.query_task(j["task_id"])
            except Exception as e:
                print(f"  [{j['uid']}] 查询异常: {str(e)[:80]}")
                continue
            s = st.get("status")
            if s in ("SUCCESS", "done", "success", "completed"):
                out = ROOT / j["out"]
                out.parent.mkdir(parents=True, exist_ok=True)
                ac.download(j["task_id"], str(out))
                j["status"] = "DONE"
                print(f"  ✅ {j['uid']} 下载完成 → {out.name}", flush=True)
            elif s in ("FAILED", "failed", "error"):
                j["status"] = "FAILED"
                print(f"  ❌ {j['uid']} 失败: {st.get('message', '')[:100]}", flush=True)
            else:
                print(f"  ⏳ {j['uid']} {s}（{st.get('duration', '?')}s）")
        BATCH_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        if all(j["status"] in ("DONE", "FAILED") for j in jobs):
            print("✅ 全部结束"); break
        time.sleep(60)
    done = sum(1 for j in jobs if j["status"] == "DONE")
    print(f"\n完成 {done}/{len(jobs)}")


if __name__ == "__main__":
    if "--submit" in sys.argv:
        submit(force="--force" in sys.argv)
    elif "--collect" in sys.argv:
        collect()
    else:
        print(__doc__)
