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
from lib.cast import cast_shot, neutralize_refs_for_silent, resolve_refs, resolve_voice
from lib.llm import chat_json
from lib.tools import ffmpeg
from s4_generate.autodl_client import generate_video, generate_video_smart

HARD = ("CRITICAL — NO ON-SCREEN TEXT: the video must contain absolutely NO text of any kind "
        "anywhere in any frame — no subtitles, no captions, no on-screen dialogue text, "
        "no Chinese characters, no floating text, no lower-third graphics, no burned-in words. "
        "The spoken dialogue exists ONLY as audio and must NEVER be visualized as subtitles, "
        "captions, speech bubbles or any on-screen text — even when people are talking, "
        "keep the frame completely text-free. "
        "Also: render no watermarks, stickers, price tags, platform logos, UI elements or QR codes; "
        "keep the product's own brand lettering exactly as it appears in the reference image; "
        "the product must always keep its exact electric-wheelchair form from the reference images "
        "— four small wheels, seat frame and armrests visible — and must never turn into a bicycle, "
        "scooter, motorcycle or any other vehicle; "
        "no background music; everyone keeps complete visual consistency with the reference images.")

PROMPT_SYSTEM = """你是 H3 视频提示词工程师。把分镜镜头字段扩写成 MiniMax H3 三段式提示词。

先理解 creative_design：开场钩子、逐镜节拍、反转与新意要体现在可见动作、人物反应和音效里；不要只换对白却把画面拍成旧模板。保持每镜信息密度，动作衔接利落，但必须遵守下面的构图、人物与产品硬约束。

【构图（宽严标准：人物全身占画面高度约1/2，允许±30%偏差；重点是叙事与对白，不为构图反复重跑）】
每镜 integrated_multimodal_description 的镜头语言以大全景描述开头（英文）：
"Wide shot: camera at a far distance, every person's full body from head to toe fully visible with environment around; each figure occupies roughly half of the frame height."
运镜只用大全景内轻缓运动（static / gentle pan / slow subtle push），不写特写/推近类运镜。

【输出格式（每镜一个字符串，严格三段）】
integrated_multimodal_description: [Shot N] Live-action documentary drama, <上述大全景构图描述 + 该镜运镜/光线/场景，英文>。A <年龄> <族裔 Caucasian/Asian> <性别> (<S1>) (the appearance MUST exactly match the reference image and this character archive: <从 cast 清单取该角色的 trait/外貌描述>) in <服装>，<动作>，and says <语气描述> at a slightly brisk pace (clear articulation, a bit faster than natural) : <d>[Chinese] 台词</d> <说话后的收尾动作+嘴唇闭合声明>。<其他人物：保持安静、嘴唇闭合>。Everyone keeps their exact faces, hairstyles and clothing from the reference images; <产品外观声明>。Only <说话人> speaks; nobody else moves their mouth.

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
   (e) 产品始终在画面内与人物同框（大全景内可见）
5. 每镜是独立视频（时长给定），动作在时长内完成，不跨镜连续
6. **读音规则（严格遵守）**：
   - 数字：218 一律写"二幺八"（号码中的"一"读"幺"）；13.8 写"十三点八"；"十"字发音清晰（shí）
   - 多音字按语义读；如需注音，写在 <d> 标签**外**（H3 只朗读 <d> 内文本，注音不能进 <d>）：
     重=zhòng（重量义，如"有多沉/多重zhòng"）；行=xíng（行走）行=háng（行业）；还=hái（还是）；长=cháng（长度）；为=wèi（因为）
   - **品牌收尾**：推荐品牌用"爱优护轻便侠"（品牌名），不报型号数字
7. 语速与节奏 slightly brisk（偏快一点点、咬字清晰，不拖沓）；**即说即停**（宝哥规则）：
   - 镜头开头：简短准备动作后立刻开口（开头静默 ≤0.5s）
   - 台词说完立即收尾/定格（结尾静默 ≤0.5s，不要长时间无声空镜）
   - 句间停顿短促，不拖长音
   提示词中写明 "starts speaking almost immediately after a brief action, and finishes the line right before the shot ends; short pauses between phrases, no long silences or trailing quiet"
8. **禁画面字幕（硬要求）**：H3 常把对白"画"成画面内字幕——每镜 integrated 段必须附上：
   "No on-screen text or subtitles anywhere in frame; the dialogue is audio only, never visualized as text."
   （后期统一烧录字幕，生成画面必须无任何文字）
9. **人物外貌规则（硬要求）**：每个人物的族裔/年龄/发型/服装必须从 cast 清单中该角色档案取：
   - 角色 id 以 western_ 开头（或 region=欧美）→ 必须写 **Caucasian/European**（如 "A 45-year-old Caucasian man with brown hair and grey temples"），**严禁写成 Chinese**
   - 中国角色 → Chinese
   - 每镜写 "the appearance must exactly match the reference photo"（参考图优先于文字）

返回 JSON：{"prompts": {"1": "...第1镜完整提示词...", "2": "...", ...}}"""


# ── 宝哥规则（2026-09-24）：有新旧车对比时，新车必须用爱优护轻便侠参考图去生 ──
# 缺参考图 H3 会把折叠车自由发挥成自行车/踏板车（历史事故 → 8c）；这里做代码级兜底，
# 只在"视觉字段"命中新车动作时补图（台词提到但画面没车反应的镜头不补，避免多图干扰）。
NEW_CAR_KEYWORDS = (
    "折叠", "展开", "车架", "新车", "轻便侠", "一键", "单手", "拎", "甩开", "抬起", "滑进后备箱",
)
NEW_CAR_DEFAULT_REFS = ["折叠", "正侧"]  # 折叠态 + 展开态双图，锚定同一台车


def ensure_new_car_ref(shot: dict) -> dict:
    """新车出镜镜头若无 product_ref，自动补爱优护轻便侠参考图（宝哥规则 2026-09-24）"""
    if shot.get("product_ref"):
        return shot
    blob = " ".join(str(shot.get(k) or "") for k in
                    ("purpose", "camera", "start_state", "end_state"))
    if not any(k in blob for k in NEW_CAR_KEYWORDS):
        return shot
    patched = dict(shot)
    patched["product_ref"] = list(NEW_CAR_DEFAULT_REFS)
    print(f"  [镜{shot.get('seq')}] 新车镜头自动补产品参考图: {NEW_CAR_DEFAULT_REFS}", flush=True)
    return patched


def build_prompts(storyboard: dict, retries: int = 3) -> dict[str, str]:
    """LLM 基于分镜字段生成每镜完整 H3 提示词（不合格自动重试）"""
    import re as _re

    from lib.cast import _apply_role_group, _role_group_for, cast_menu
    cast_ctx = cast_menu()
    # 角色组替换：给 LLM 看替换后的角色（欧美组→western_* 档案，避免写"中国男性"矛盾）
    _group = _role_group_for(storyboard.get("job_uid", ""))
    _core = ("son", "mother", "elder")

    def _grp_text(t: str) -> str:
        if not _group:
            return t
        for b in _core:
            repl = _group.get(b)
            if repl:
                t = _re.sub(rf"(?<![a-z_]){b}(?![a-z_])", repl, t)
                t = t.replace({"son": "S1", "mother": "S2", "elder": "S3"}[b], repl)
        return t

    shots_ctx = []
    for s in storyboard["shots"]:
        s = ensure_new_car_ref(s)
        shots_ctx.append({
            "seq": s["seq"], "duration": s["duration"],
            "purpose": s["purpose"], "shot_size": s["shot_size"], "camera": s["camera"],
            "start_state": s["start_state"], "end_state": s["end_state"],
            "speaker": _grp_text(s["speaker"]), "narration": s["narration"],
            "cast_refs": [_apply_role_group(r, _group) if not r.startswith("@") else r
                          for r in s.get("cast_refs", [])],
            "sound_design": s["sound_design"],
            "has_product": bool(s.get("product_ref")),
        })
    payload = {
        "concept": storyboard.get("concept", ""),
        "creative_design": storyboard.get("creative_design", {}),
        "cast": cast_ctx,
        "shots": shots_ctx,
        "HARD_SECTION": HARD,
    }
    last_err = None
    for attempt in range(1, retries + 1):
        out = chat_json([
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": "分镜数据：\n" + json.dumps(payload, ensure_ascii=False, indent=1)},
        ], temperature=0.35, max_tokens=8000)
        prompts = out.get("prompts", {})
        # 校验：每镜都有 + 含 <d>；并清理多余输出（只保留分镜里实际存在的 seq）
        try:
            cleaned = {}
            for s in storyboard["shots"]:
                seq = str(s["seq"])
                p = prompts.get(seq, "")
                if not p or "<d>" not in p:
                    raise RuntimeError(f"镜{seq} 不合格（缺 <d> 或为空）")
                # 代码层强制附 HARD 段（LLM 经常漏附——硬约束必须进 H3 提示词）
                if "NO ON-SCREEN TEXT" not in p:
                    p = p.rstrip() + "\n\n" + HARD
                # 族裔兜底：欧美组角色禁止 Chinese 描述（LLM 惯性照抄模板）
                # 注意：storyboard 的 cast_refs 是原始核心名（组替换发生在 cast_shot），
                # 所以以 storyboard 的 role_group 字段判断
                refs_str = " ".join(s.get("cast_refs", []))
                group_name = str(storyboard.get("role_group", ""))
                if "western_" in refs_str or "欧美" in group_name:
                    p = (p.replace("Chinese man", "Caucasian man")
                          .replace("Chinese woman", "Caucasian woman")
                          .replace("Chinese person", "Caucasian person"))
                cleaned[seq] = p
        except RuntimeError as e:
            last_err = e
            print(f"  ⚠ 提示词第{attempt}次不合格（{e}），重试...", flush=True)
            continue
        if len(prompts) > len(cleaned):
            print(f"  （LLM 多输出 {len(prompts) - len(cleaned)} 条已过滤）", flush=True)
        if attempt > 1:
            print(f"  ✓ 第{attempt}次重试成功", flush=True)
        return cleaned
    raise RuntimeError(f"提示词生成失败（重试{retries}次仍不合格）: {last_err}")


def gen_shot(shot: dict, prompt: str, out_dir: Path, job_uid: str = "") -> dict:
    seq = shot["seq"]
    out_path = out_dir / f"shot_{seq:02d}.mp4"
    if out_path.exists() and out_path.stat().st_size > 100 * 1024:
        return {"seq": seq, "status": "cached", "path": str(out_path)}

    # 选角：@slot → 具体角色（同 job 内同槽位一致，跨 job 轮换）
    shot = cast_shot(shot, job_uid)
    if shot.get("_cast_mapping"):
        print(f"  [镜{seq}] 选角: {shot['_cast_mapping']}", flush=True)

    # 新车必带参考图（宝哥规则 2026-09-24）——放在取 refs 之前
    shot = ensure_new_car_ref(shot)

    # 非说话人 → quiet 闭嘴版参考图（防 H3 把情绪图的张嘴表情带歪）
    refs_raw = neutralize_refs_for_silent(shot["cast_refs"], shot["speaker"])
    if refs_raw != shot["cast_refs"]:
        print(f"  [镜{seq}] 非说话人闭嘴化: {shot['cast_refs']} → {refs_raw}", flush=True)
    refs = [str(p) for p in resolve_refs(refs_raw)]
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


def _probe_silences(video: Path):
    """silencedetect 解析 → ([(start,end)...], duration)"""
    import re
    r = subprocess.run([ffmpeg(), "-i", str(video), "-af", "silencedetect=n=-35dB:d=0.25",
                        "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    text = r.stderr or ""
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    out, cur = [], None
    for ln in text.splitlines():
        m1 = re.search(r"silence_start:\s*(-?[\d.]+)", ln)
        if m1:
            cur = max(0.0, float(m1.group(1)))
        m2 = re.search(r"silence_end:\s*([\d.]+)", ln)
        if m2 and cur is not None:
            out.append((cur, float(m2.group(1))))
            cur = None
    return out, dur


def trim_shot_edges(video: Path, pad: float = 0.15) -> bool:
    """裁掉镜头头尾静默（保留 pad 秒缓冲；说话间停顿不动）

    宝哥规则 2026-09-23：开头/分镜间/结尾停顿要短，整体节奏流畅。
    幂等：处理后写 .trimmed 标记，重复调用跳过。
    """
    flag = video.with_suffix(".trimmed")
    if flag.exists():
        return False
    silences, dur = _probe_silences(video)
    if dur <= 0 or not silences:
        flag.write_text("no-trim")
        return False
    keep_start, keep_end = 0.0, dur
    if silences[0][0] <= 0.08:  # 贴边头部静默
        keep_start = max(0.0, silences[0][1] - pad)
    if silences[-1][1] >= dur - 0.08:  # 贴边尾部静默
        keep_end = min(dur, silences[-1][0] + pad)
    if keep_start <= 0.05 and keep_end >= dur - 0.05:
        flag.write_text("no-trim")
        return False
    tmp = video.with_name(video.stem + ".trimtmp.mp4")
    r = subprocess.run([ffmpeg(), "-y", "-ss", f"{keep_start:.3f}", "-to", f"{keep_end:.3f}",
                        "-i", str(video), "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                        "-c:a", "aac", "-b:a", "128k", str(tmp)],
                       capture_output=True, text=True, errors="replace")
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 50 * 1024:
        tmp.replace(video)
        flag.write_text(f"trimmed {keep_start:.3f}-{keep_end:.3f}")
        print(f"  ✂ 静默裁剪 {video.name}: {dur:.2f}s → {keep_end - keep_start:.2f}s", flush=True)
        return True
    return False


def concat_shots(shots: list[dict], out_dir: Path, final_name: str = "final.mp4") -> Path:
    # 节奏优化：拼接前裁头尾静默（宝哥规则）
    for s in shots:
        p = out_dir / "shots" / f"shot_{s['seq']:02d}.mp4"
        if p.exists():
            try:
                trim_shot_edges(p)
            except Exception as e:
                print(f"  ⚠ 镜{s['seq']} 静默裁剪失败（跳过）: {str(e)[:80]}", flush=True)
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
    if not (sb.get("template_id") and sb.get("creative_research") and sb.get("creative_design")):
        raise RuntimeError("仅支持已完成知识库研究与创意设计的模板分镜；旧分镜禁止直接出片")
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
