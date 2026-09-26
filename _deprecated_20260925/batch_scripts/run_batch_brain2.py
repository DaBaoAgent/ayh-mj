"""脑洞10连第二批 — 批量提交 + 轮询下载

用法：
  python tools/run_batch_brain2.py --submit    # 提交全部（10 条）
  python tools/run_batch_brain2.py --collect   # 轮询并下载全部完成的
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac  # noqa: E402

BATCH_FILE = ROOT / "state/batch_brain2_jobs.json"

UIDS = [
    "B2_01_kuaidi", "B2_02_diaoyu", "B2_03_luying", "B2_04_chongdian", "B2_05_xueche",
    "B2_06_zhaiXiang", "B2_07_jiedian", "B2_08_nianhuo", "B2_09_xiuche", "B2_10_jiaoChe",
]


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


def submit() -> None:
    jobs = []
    if BATCH_FILE.exists():
        jobs = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    have = {j["uid"] for j in jobs}
    for uid in UIDS:
        if uid in have:
            print(f"  跳过（已提交）: {uid}")
            continue
        spec_path = ROOT / f"state/onetake_prompt_job_{uid}.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        print(f"🧩 提交 {uid} ...", flush=True)
        payload = build_payload(spec)
        tid = ac.create_task(spec["workflow"], payload)
        jobs.append({"uid": uid, "task_id": tid, "status": "RUNNING",
                     "title": uid, "out": f"out/gen_job_{uid}/onetake.mp4"})
        BATCH_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  ✓ {uid} → {tid}")
    print(f"\n已提交 {len(jobs)}/10")


def collect() -> None:
    jobs = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    for rnd in range(400):  # 最多 ~6.6 小时
        pending = [j for j in jobs if j["status"] != "DONE"]
        if not pending:
            print("✅ 全部完成"); break
        for j in jobs:
            if j["status"] == "DONE":
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
        submit()
    elif "--collect" in sys.argv:
        collect()
    else:
        print(__doc__)
