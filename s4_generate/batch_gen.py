"""逐镜头视频生成：storyboard → H3 批量出片

每个镜头：
  1. 解析 product_ref → 产品白底图路径
  2. 调 AutoDL H3（多图参考）生成 2-5 秒镜头
  3. 并发 3 路（AutoDL 实测支持并发）
  4. 全部完成后更新 job.shots + status=generate

用法：
    python s4_generate/batch_gen.py --uid job_xxx      # 指定任务
    python s4_generate/batch_gen.py --top 1            # 批量
    python s4_generate/batch_gen.py --uid xxx --dry    # 演练（只打印，不花钱）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import OUT_DIR, ASSETS_DIR
from lib.state import get_job, update_job, list_jobs, connect
from s3_storyboard.split import PRODUCT_REFS
from s4_generate.autodl_client import generate_video

SHOTS_DIR_NAME = "shots"


def resolve_product_ref(ref_name: str) -> str | None:
    """product_ref 名称 → 产品图绝对路径"""
    if not ref_name:
        return None
    filename = PRODUCT_REFS.get(ref_name)
    if not filename:
        return None
    path = ASSETS_DIR / "products" / filename
    return str(path) if path.exists() else None


def gen_shot(uid: str, shot: dict, dry: bool = False) -> dict:
    """生成单个镜头"""
    seq = shot["seq"]
    out_dir = OUT_DIR / uid / SHOTS_DIR_NAME
    out_path = out_dir / f"shot_{seq:02d}.mp4"

    # 已完成跳过（断点续传）
    if out_path.exists() and out_path.stat().st_size > 100 * 1024:
        return {"seq": seq, "status": "cached", "video_path": str(out_path)}

    ref_images = []
    ref = resolve_product_ref(shot.get("product_ref", ""))
    if ref:
        ref_images.append(ref)

    prompt = shot["scene_prompt"]
    duration = min(10, max(1, int(shot.get("duration", 3))))

    if dry:
        return {"seq": seq, "status": "dry", "prompt": prompt,
                "ref": shot.get("product_ref"), "duration": duration}

    # 无参考图 → 走文生视频工作流（multi_image 的 ref_image_0 是必填，缺了报"缺少必填参数"）
    workflow = "multi_image" if ref_images else "text2video"

    result = generate_video(
        prompt=prompt,
        ref_images=ref_images,
        duration=duration,
        resolution="768p竖",
        out_path=str(out_path),
        workflow=workflow,
    )
    return {"seq": seq, "status": "ok", **result}


def process_job(uid: str, dry: bool = False, concurrency: int = 3) -> dict:
    """处理单个任务的全部镜头"""
    job = get_job(uid)
    if not job:
        raise ValueError(f"任务不存在: {uid}")
    storyboard = job.get("storyboard")
    if not storyboard:
        raise ValueError(f"任务 {uid} 没有分镜（先跑 s3_storyboard/split.py）")

    sb = json.loads(storyboard) if isinstance(storyboard, str) else storyboard
    shots = sb.get("shots", [])
    if not shots:
        raise ValueError(f"任务 {uid} 分镜为空")

    print(f"  🎥 {uid}: {len(shots)} 个镜头（并发 {concurrency}）", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(gen_shot, uid, shot, dry): shot for shot in shots}
        for future in as_completed(futures):
            shot = futures[future]
            try:
                r = future.result()
                results.append(r)
                if r["status"] == "ok":
                    print(f"      ✓ 镜头{shot['seq']}: {r.get('cost', 0)}元 {r.get('task_id', '')[:12]}", flush=True)
                elif r["status"] == "cached":
                    print(f"      ↻ 镜头{shot['seq']}: 已存在，跳过", flush=True)
                elif r["status"] == "dry":
                    print(f"      (演练) 镜头{shot['seq']}: {shot['duration']}s [{shot.get('product_ref') or '无产品'}]", flush=True)
            except Exception as e:
                print(f"      ✗ 镜头{shot['seq']} 失败: {str(e)[:70]}", flush=True)
                results.append({"seq": shot["seq"], "status": "failed", "error": str(e)[:100]})

    results.sort(key=lambda x: x["seq"])
    ok_count = sum(1 for r in results if r["status"] in ("ok", "cached"))
    total_cost = sum(r.get("cost", 0) for r in results)

    if not dry and ok_count == len(shots):
        # 全部成功才推进状态
        update_job(uid, status="generate",
                   shots=json.dumps(results, ensure_ascii=False))

    print(f"      完成 {ok_count}/{len(shots)}，成本 ¥{total_cost:.2f}", flush=True)
    return {"uid": uid, "shots": results, "ok": ok_count,
            "total": len(shots), "cost": total_cost}


def run(top: int = 1, uid: str = None, dry: bool = False, concurrency: int = 3) -> dict:
    """批量处理"""
    if uid:
        uids = [uid]
    else:
        jobs = list_jobs("storyboard", limit=top)
        if not jobs:
            jobs = [j for j in list_jobs("copy", limit=top) if j.get("script")]
            print("⚠ 没有已分镜任务（status=storyboard），先跑分镜", flush=True)
            return {"processed": 0}
        uids = [j["uid"] for j in jobs[:top]]

    print(f"🎥 生成视频: {len(uids)} 个任务", flush=True)
    results = []
    for u in uids:
        try:
            results.append(process_job(u, dry=dry, concurrency=concurrency))
        except Exception as e:
            print(f"  ✗ {u}: {str(e)[:80]}", flush=True)

    return {"processed": len(results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="逐镜头视频生成")
    parser.add_argument("--uid", help="任务UID")
    parser.add_argument("--top", type=int, default=1, help="批量数量")
    parser.add_argument("--dry", action="store_true", help="演练模式（不花钱）")
    parser.add_argument("--concurrency", type=int, default=3, help="并发数")
    args = parser.parse_args()

    result = run(top=args.top, uid=args.uid, dry=args.dry, concurrency=args.concurrency)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
