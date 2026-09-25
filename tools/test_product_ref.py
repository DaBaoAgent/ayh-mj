"""产品保真对照测试 A/B/C — 480p × 5s（验证「展开态参考图缺失」假设）

背景：T07 成片车"不像爱优护轻便侠"（观众视角=普通手动轮椅）。
假设：T07 参考图只给了「折叠」单图 → 展开态无锚定，H3 脑补成通用轮椅；
      T06 曾用「折叠+正侧」双图（车略好）→ 需对照验证。

三组仅"产品参考图组合"不同，其余全同（人物图/台词/提示词/参数）：
  A = 折叠 单图        （T07 现状，复现问题）
  B = 折叠 + 正侧双图   （T06 组合）
  C = 折叠 + 正侧 + 45度（全产品图）

用法: .venv/Scripts/python.exe tools/test_product_ref.py [--dry]
输出: out/tests/product_ref_{A,B,C}.mp4 + product_ref_task.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

WF = "minimax_h3_image_audio_to_video_v2_15s"
MAN = "assets/cast/emotions/son_full.png"
VOICE = "assets/cast/voice/son_voice.mp3"

PROMPT_TMPL = (
    "Live-action vertical short video, natural daylight at a residential doorway. "
    "One single continuous shot, no cuts. A 50-year-old Chinese man in dark blue work "
    "clothes, matching the FIRST reference image, stands at a doorway and unfolds a "
    "silver-grey electric wheelchair: he lifts the folded frame up, it opens with its "
    "four wheels settling onto the ground and the seat frame locking into place, then "
    "he steps back and gestures proudly at the unfolded wheelchair facing the camera. "
    "Brisk timing: he speaks starting within the first quarter second and finishes "
    "right before the video ends, no trailing silence. Exactly two subjects in the "
    "whole frame — the man and the wheelchair — the man appears exactly once, no other "
    "people, no duplicates, no clones, no extra figures anywhere in the frame, "
    "background or edges. The wheelchair must exactly match {PRODUCT_REFS}: silver-grey "
    "metal frame, black seat and backrest, four wheels, the distinctive RED "
    "shock-absorbing springs on the frame, brand lettering on the frame preserved "
    "exactly as in the reference image; it is an electric wheelchair with a motor in "
    "its rear wheels, never a plain manual wheelchair, never a bicycle, scooter or any "
    "other vehicle; after unfolding, its full silhouette faces the camera with all four "
    "wheels on the ground. The man says in a cheerful, proud tone at a slightly brisk "
    "pace: <d>[Chinese] 这就是爱优护轻便侠，单手就能展开。</d> Only the man speaks; his "
    "mouth moves while speaking. No on-screen text or subtitles; no watermarks; no "
    "logos other than the product's own brand lettering. Camera: low wide shot, the "
    "man's full body from head to toe visible, the wheelchair fully in frame."
)

GROUPS = {
    "A": dict(
        product_images=["assets/products/折叠-无阴影.png"],
        refs_phrase="the SECOND reference image",
    ),
    "B": dict(
        product_images=["assets/products/折叠-无阴影.png",
                        "assets/products/正侧-3-无阴影.png"],
        refs_phrase="the SECOND and THIRD reference images",
    ),
    "C": dict(
        product_images=["assets/products/折叠-无阴影.png",
                        "assets/products/正侧-3-无阴影.png",
                        "assets/products/45度-加水杯-无阴影.png"],
        refs_phrase="the SECOND, THIRD and FOURTH reference images",
    ),
}


def build_payload(g: dict) -> dict:
    imgs = [MAN, *g["product_images"]]
    payload = {
        "prompt": PROMPT_TMPL.format(PRODUCT_REFS=g["refs_phrase"]),
        "duration": 5,
        "resolution": "480p竖",
    }
    for i, img in enumerate(imgs):
        payload[f"ref_image_{i}"] = ac.to_data_url(str(ROOT / img))
    payload["ref_audio_0"] = ac.to_data_url(str(ROOT / VOICE), resize=False)
    return payload


def main(dry: bool = False) -> None:
    out_dir = ROOT / "out" / "tests"
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = {}
    for k, g in GROUPS.items():
        payload = build_payload(g)
        imgs = ["son_full", *[Path(p).stem for p in g["product_images"]]]
        print(f"[{k}] 参考图 {len(imgs)}: {imgs} | 产品引用: {g['refs_phrase']}", flush=True)
        if dry:
            print(f"    (dry) payload keys: {list(payload.keys())}", flush=True)
            continue
        tid = ac.create_task(WF, payload)
        tasks[k] = tid
        print(f"[{k}] ✓ task_id: {tid}", flush=True)

    if dry:
        return
    (out_dir / "product_ref_task.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")

    # 顺序轮询（三条任务在服务端已并发执行）
    for k, tid in tasks.items():
        print(f"[{k}] 等待完成...", flush=True)
        url = ac.poll_task(tid, interval=20)
        out = out_dir / f"product_ref_{k}.mp4"
        ac.download(url, str(out))
        print(f"[{k}] ✓ 下载: {out}", flush=True)
    print("全部完成。对比命令见 docs/test-product-ref.md", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
