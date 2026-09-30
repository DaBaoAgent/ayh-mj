"""单条多镜头生成器（新工艺 one-take）— 薄 CLI 包装。

实现已收敛到 `lib/orchestrator/generation.py::IdempotentGenerator`（唯一事实源）：
提交前算 fingerprint、拿到 task_id 立即落 `provider_tasks`、崩溃重启只 query 不复提交、
下载失败只重下。这样"命令行手动跑"和"编排器自动跑"是同一条代码路径。

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

# H3 服务端 prompt 硬上限 / 安全线（与 generation.py / make_15s 同口径）
PROMPT_MAX = 10000
PROMPT_SAFE = 9800


def run(spec_path: str, dry: bool = False) -> Path:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    uid = spec["job_uid"]
    out_dir = ROOT / "out" / f"gen_{uid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "onetake.mp4"

    n_prompt = len(str(spec.get("prompt") or ""))
    print(f"🧩 one-take 生成：{uid} | {spec.get('duration')}s | {spec.get('resolution')} | "
          f"参考图 {len(spec.get('ref_images') or [])} + 音频 {len(spec.get('ref_audios') or [])} | "
          f"prompt {n_prompt}/{PROMPT_MAX} 字符" + (" ✓" if n_prompt <= PROMPT_SAFE else " ⚠️ 接近上限"),
          flush=True)
    if dry:
        print("  (dry) 不提交。", flush=True)
        return out

    from lib.jobstore import store
    from lib.orchestrator import AutoDLProvider, IdempotentGenerator
    from lib.orchestrator.errors import PromptTooLong

    if store.get_job(uid) is None:
        store.create_job(goal=spec.get("goal") or f"cli:{uid}", uid=uid)

    gen = IdempotentGenerator(store, AutoDLProvider(), root=ROOT, poll_interval=20, log=print)
    try:
        outcome = gen.generate(
            uid=uid, prompt=str(spec.get("prompt") or ""),
            duration=int(spec.get("duration") or 15),
            resolution=str(spec.get("resolution") or "768p竖"),
            workflow=str(spec.get("workflow") or "multi_image_15s"),
            fallback_workflows=spec.get("fallback_workflows") or [],
            ref_images=spec.get("ref_images") or [],
            ref_audios=spec.get("ref_audios") or [],
            out_path=out)
    except PromptTooLong as exc:
        raise SystemExit(
            f"✗ {exc.message}\n"
            "  压缩手法（不删镜头/不改台词/强度不降）见 skills/media/ayh-mj：\n"
            "   ① pp.compose(cold_open=False) 去掉全局 COLD OPEN 段（镜 1 自带特写）\n"
            "   ② 每镜 SPEAKER LOCK 长声明压成一句 + CAST 段加一条全局 SPEAKER RULE\n"
            "   ③ 状态/动作类硬约束只留「几次、每次完整、不许空动」，细节放各镜 desc\n"
            "   ④ 每镜终态句压成一句；⑤ WHEEL 段删括号解释合并重复") from exc

    (out_dir / "onetake_task.json").write_text(json.dumps(
        {"task_id": outcome.task_id, "workflow": outcome.workflow, "spec": spec_path,
         "resumed": outcome.reused}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "onetake_result.json").write_text(json.dumps(
        {"task_id": outcome.task_id, "workflow": outcome.workflow,
         "video_path": str(out), "duration": spec.get("duration"),
         "cost_est": outcome.cost, "resumed": outcome.reused},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ 成片: {out}（工作流 {outcome.workflow}，预估 ¥{outcome.cost}）", flush=True)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    run(args[0], dry="--dry" in sys.argv)
