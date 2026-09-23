"""通用逐镜生成器 — 分镜 JSON → H3 提示词 → 逐镜生成（含音色克隆）→ 拼接

固化点：
  · 人物一致性：cast_refs 自动解析定妆图/情绪图（lib/cast.py）
  · 声音一致性：speaker 自动挂音色样本（ref_audio_0 + zm_u08 工作流）
  · 镜头语言：LLM 把导演字段（景别/机位/起终点）扩写成 H3 三段式提示词

用法：
  python s4_generate/gen_from_storyboard.py state/storyboard_xxx.json
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.cast import cast_shot, resolve_refs, resolve_voice
from lib.llm import chat_json
from lib.tools import ffmpeg
from s4_generate.autodl_client import generate_video, generate_video_smart

HARD = ("Hard constraints: render no watermarks, subtitles, captions, floating text, letters, "
        "numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; "
        "keep the product's own brand lettering exactly as it appears in the reference image; "
        "the product must always keep its exact electric-wheelchair form from the reference images "
        "— four small wheels, seat frame and armrests visible — and must never turn into a bicycle, "
        "scooter, motorcycle or any other vehicle; "
        "no background music; everyone keeps complete visual consistency with the reference images.")

PROMPT_SYSTEM = """你是 H3 视频提示词工程师。把分镜镜头字段扩写成 MiniMax H3 三段式提示词。

【输出格式（每镜一个字符串，严格三段）】
integrated_multimodal_description: [Shot N] Live-action documentary drama, <镜头语言：景别/机位/运镜/光线/场景，英文>。A <年龄> Chinese <性别> (<S1>) in <服装>，<动作>，and says <语气描述> at a natural pace: <d>[Chinese] 台词</d> <说话后的收尾动作+嘴唇闭合声明>。<其他人物：保持安静、嘴唇闭合>。Everyone keeps their exact faces, hairstyles and clothing from the reference images; <产品外观声明>。Only <说话人> speaks; nobody else moves their mouth.

overall_soundscape: <具体音效（从 sound_design 扩写），英文>

non_diegetic_music: N/A

<HARD 段原样附上>

【规则】
1. 台词逐字放入 <d>[Chinese] ...</d>，<d> 外只写动作/语气，禁止重复台词文字
2. 单人说话：场景里其他人必须写 "silent, mouth closed" 或 "keeps lips closed"
3. 说话人+语气：从 narration 的语气和 speaker 推断（如质问→shouts urgently）
4. **产品镜头强制规则**（违反=失败）：
   (a) 产品外观声明必须写 "keeps its exact electric-wheelchair form from the reference images"
   (b) 折叠/展开动作必须落到具体轮椅特征：展开后 "its four small wheels settle onto the ground, the seat frame locks into place"
   (c) 动作描述只用 "unfolds/folds the electric wheelchair frame"，严禁 bicycle/scooter/bike 等词
   (d) 画面里必须能看到轮椅特征（四个小轮/座椅框/扶手），不能只拍一个光秃秃的车架
5. 每镜是独立视频（时长给定），动作在时长内完成，不跨镜连续
6. 数字读法：218→二一八（台词已是中文则原样）

返回 JSON：{"prompts": {"1": "...第1镜完整提示词...", "2": "...", ...}}"""


def build_prompts(storyboard: dict) -> dict[str, str]:
    """LLM 基于分镜字段生成每镜完整 H3 提示词"""
    from lib.cast import cast_menu
    cast_ctx = cast_menu()
    shots_ctx = []
    for s in storyboard["shots"]:
        shots_ctx.append({
            "seq": s["seq"], "duration": s["duration"],
            "purpose": s["purpose"], "shot_size": s["shot_size"], "camera": s["camera"],
            "start_state": s["start_state"], "end_state": s["end_state"],
            "speaker": s["speaker"], "narration": s["narration"],
            "sound_design": s["sound_design"],
            "has_product": bool(s.get("product_ref")),
        })
    payload = {
        "concept": storyboard.get("concept", ""),
        "cast": cast_ctx,
        "shots": shots_ctx,
        "HARD_SECTION": HARD,
    }
    out = chat_json([
        {"role": "system", "content": PROMPT_SYSTEM},
        {"role": "user", "content": "分镜数据：\n" + json.dumps(payload, ensure_ascii=False, indent=1)},
    ], temperature=0.4, max_tokens=4000)
    prompts = out.get("prompts", {})
    # 校验：每镜都有 + 含 <d>
    for s in storyboard["shots"]:
        seq = str(s["seq"])
        p = prompts.get(seq, "")
        if not p or "<d>" not in p:
            raise RuntimeError(f"镜{seq} 提示词生成不合格（缺 <d> 或为空）")
    return prompts


def gen_shot(shot: dict, prompt: str, out_dir: Path, job_uid: str = "") -> dict:
    seq = shot["seq"]
    out_path = out_dir / f"shot_{seq:02d}.mp4"
    if out_path.exists() and out_path.stat().st_size > 100 * 1024:
        return {"seq": seq, "status": "cached", "path": str(out_path)}

    # 选角：@slot → 具体角色（同 job 内同槽位一致，跨 job 轮换）
    shot = cast_shot(shot, job_uid)
    if shot.get("_cast_mapping"):
        print(f"  [镜{seq}] 选角: {shot['_cast_mapping']}", flush=True)

    refs = [str(p) for p in resolve_refs(shot["cast_refs"])]
    # 产品参考图（product_ref：字符串或数组）——必须传入，否则 H3 会自由发挥
    product_ref = shot.get("product_ref") or ""
    if product_ref:
        pref_list = product_ref if isinstance(product_ref, list) else [product_ref]
        refs += [str(p) for p in resolve_refs(pref_list)]
    voice = resolve_voice(shot["speaker"])

    # 显式指定 workflow 时直连；否则走智能路由（自动选流+失败切换）
    explicit_wf = shot.get("workflow")
    if explicit_wf:
        result = generate_video(
            prompt=prompt, ref_images=refs,
            ref_audio=str(voice) if voice else None,
            duration=int(float(shot["duration"])),
            resolution="768p竖", out_path=str(out_path), workflow=explicit_wf)
        result["used_workflow"] = explicit_wf
    else:
        if voice:
            print(f"  [镜{seq}] 音色克隆: {voice.name}", flush=True)
        result = generate_video_smart(
            prompt=prompt, ref_images=refs,
            ref_audio=str(voice) if voice else None,
            duration=int(float(shot["duration"])),
            quality=shot.get("quality", "standard"),
            out_path=str(out_path))
        print(f"  [镜{seq}] 路由: {result.get('used_workflow')}", flush=True)
    return {"seq": seq, "status": "ok", **result}


def concat_shots(shots: list[dict], out_dir: Path, final_name: str = "final.mp4") -> Path:
    concat_list = out_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file 'shots/shot_{s['seq']:02d}.mp4'" for s in shots),
        encoding="utf-8")
    final = out_dir / final_name
    cmd = [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
           "-c", "copy", str(final.name)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(out_dir))
    if r.returncode != 0:
        # 重编码兜底
        cmd = [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
               "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
               "-c:a", "aac", "-b:a", "128k", str(final.name)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(out_dir))
        if r.returncode != 0:
            raise RuntimeError(f"拼接失败: {r.stderr[-400:]}")
    return final


def run(storyboard_path: str, skip_prompt_build: bool = False,
        concurrency: int = 6) -> Path:
    sb = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    uid = sb.get("job_uid") or Path(storyboard_path).stem
    out_dir = ROOT / "out" / f"gen_{uid}"
    (out_dir / "shots").mkdir(parents=True, exist_ok=True)

    prompts_file = out_dir / "prompts.json"
    if prompts_file.exists() and skip_prompt_build:
        prompts = json.loads(prompts_file.read_text(encoding="utf-8"))
    else:
        print("📝 LLM 生成 H3 提示词...", flush=True)
        prompts = build_prompts(sb)
        prompts_file.write_text(json.dumps(prompts, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        print(f"  ✓ {len(prompts)} 镜提示词就绪", flush=True)

    print(f"🎬 逐镜生成（{sb.get('template_name', uid)}，并发 {concurrency}）...", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(gen_shot, s, prompts[str(s["seq"])], out_dir / "shots", uid): s
                   for s in sb["shots"]}
        for f in as_completed(futures):
            s = futures[f]
            try:
                r = f.result()
                results.append(r)
                print(f"  ✓ 镜{r['seq']}: {r['status']} {r.get('cost', 0)}元", flush=True)
            except Exception as e:
                print(f"  ✗ 镜{s['seq']} 失败: {str(e)[:150]}", flush=True)
                results.append({"seq": s["seq"], "status": "failed", "error": str(e)[:300]})

    results.sort(key=lambda x: x["seq"])
    (out_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = [r for r in results if r["status"] in ("ok", "cached")]
    if len(ok) < len(sb["shots"]):
        raise RuntimeError(f"仅 {len(ok)}/{len(sb['shots'])} 镜成功，取消拼接（重跑续传）")

    final = concat_shots(sb["shots"], out_dir)
    print(f"✓ 成片: {final}", flush=True)
    return final


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python s4_generate/gen_from_storyboard.py <storyboard.json>")
        raise SystemExit(1)
    run(sys.argv[1])
