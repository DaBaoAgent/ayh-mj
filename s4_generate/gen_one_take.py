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

# H3 服务端 prompt 硬上限（2026-09-26 实测：超限时三个 fallback 工作流全被拒，未扣费）。
# 服务端校验在提交前，报错形如「参数: prompt 的长度: 11506 大于最大长度 10000」。
PROMPT_MAX = 10000
PROMPT_SAFE = 9800        # 安全线：留 200 字符余量给后续微调



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

    n_prompt = len(payload["prompt"])
    print(f"🧩 one-take 生成：{uid} | {spec['duration']}s | {spec['resolution']} | "
          f"参考图 {len(spec['ref_images'])} + 音频 {len(spec['ref_audios'])} | "
          f"prompt {n_prompt}/{PROMPT_MAX} 字符" + (" ✓" if n_prompt <= PROMPT_SAFE else " ⚠️ 接近上限"), flush=True)
    if n_prompt > PROMPT_MAX:
        raise SystemExit(
            f"✗ prompt 长度 {n_prompt} > H3 上限 {PROMPT_MAX}：服务端会拒收（未扣费，但白等）。\n"
            "  压缩手法（不删镜头/不改台词/强度不降）见 skills/media/ayh-mj：\n"
            "   ① pp.compose(cold_open=False) 去掉全局 COLD OPEN 段（镜 1 自带特写）\n"
            "   ② 每镜 SPEAKER LOCK 长声明压成一句 + CAST 段加一条全局 SPEAKER RULE\n"
            "   ③ 状态/动作类硬约束只留「几次、每次完整、不许空动」，细节放各镜 desc\n"
            "   ④ 每镜终态句压成一句；⑤ WHEEL 段删括号解释合并重复")
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
