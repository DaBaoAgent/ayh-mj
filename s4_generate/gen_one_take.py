"""单条多镜头生成器（新工艺 one-take）— 全部镜头在一条 15s 视频里一次生成

与逐镜版（gen_from_storyboard.py）的区别：
  · 一次 H3 调用生成整条视频（含全部分镜/镜头切换）
  · 人物一致性 = 全员定妆图同批参考；声音一致性 = ref_audio_0/1 双音色克隆
  · 无拼接：产出即整片；字幕直接在整片上烧

输入：onetake 提示词 JSON（state/onetake_prompt_<uid>.json，人工精修稿）
用法：
  python s4_generate/gen_one_take.py state/onetake_prompt_job_xxx.json           # 真生成
  python s4_generate/gen_one_take.py state/onetake_prompt_job_xxx.json --dry     # 演练
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac


def run(spec_path: str, dry: bool = False) -> Path:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    uid = spec["job_uid"]
    out_dir = ROOT / "out" / f"gen_{uid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "onetake.mp4"

    payload: dict = {
        "prompt": spec["prompt"],
        "duration": int(spec["duration"]),
        "resolution": spec["resolution"],
    }
    for i, img in enumerate(spec["ref_images"][:9]):  # 工作流支持 ≤9；展开态三张产品图+角色们 = 最多 6-9 张（2026-09-24 放开）
        p = ROOT / img if not Path(img).is_absolute() else Path(img)
        payload[f"ref_image_{i}"] = ac.to_data_url(str(p))
    for i, a in enumerate(spec["ref_audios"][:3]):
        p = ROOT / a if not Path(a).is_absolute() else Path(a)
        payload[f"ref_audio_{i}"] = ac.to_data_url(str(p), resize=False)

    print(f"🧩 one-take 生成：{uid} | {spec['duration']}s | {spec['resolution']} | "
          f"参考图 {len(spec['ref_images'])} + 音频 {len(spec['ref_audios'])}", flush=True)
    if dry:
        print("  (dry) 不提交。payload 字段:", list(payload.keys()), flush=True)
        return out

    chain = [spec["workflow"], *spec.get("fallback_workflows", [])]
    last_err = None
    for wf in chain:
        try:
            print(f"  提交工作流: {wf} ...", flush=True)
            task_id = ac.create_task(wf, payload)
            print(f"  ✓ task_id: {task_id}", flush=True)
            (out_dir / "onetake_task.json").write_text(json.dumps(
                {"task_id": task_id, "workflow": wf, "spec": spec_path},
                ensure_ascii=False, indent=1), encoding="utf-8")
            url = ac.poll_task(task_id, interval=20)
            ac.download(url, str(out))
            cost = {"768p竖": 0.06, "1080p竖": 0.10}.get(spec["resolution"], 0.06) * spec["duration"]
            result = {"task_id": task_id, "workflow": wf, "video_path": str(out),
                      "duration": spec["duration"], "cost_est": round(cost, 2)}
            (out_dir / "onetake_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
            print(f"✓ 成片: {out}（工作流 {wf}，预估 ¥{result['cost_est']}）", flush=True)
            return out
        except Exception as e:
            last_err = e
            print(f"  ✗ {wf} 失败: {str(e)[:200]}", flush=True)
    raise RuntimeError(f"全部工作流失败，最后错误: {str(last_err)[:300]}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    run(args[0], dry="--dry" in sys.argv)
