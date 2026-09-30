"""阶段实现（Phase 3）。

每个 stage 都是 `f(ctx: StageContext) -> StageResult`：
  · 检查类（plan / preflight / qa / package）在本进程内完成，不花钱、可反复执行；
  · 生成与后期通过 `ctx.run_subprocess()` 调既有脚本；子进程句柄登记在 run handle 上，
    Cancel 时按进程树安全终止，不留孤儿；
  · 所有 stage 都必须幂等：产物已存在时跳过（与 make_15s 的口径一致），
    这样 resume/retry 只是"接着跑没跑完的部分"。

当前产线 = 15 秒 one-take（docs/15秒软广-产线说明.md）：
  plan(取 spec) → preflight(台词 + prompt 门禁) → generate(H3) → qa(成片校验)
  → compose(裁剪/字幕/BGM/音效/归档) → package(归档核对)
"""
from __future__ import annotations

import json
import re
from contextlib import suppress
from pathlib import Path

from .errors import (
    CLAIM_FORBIDDEN,
    CLAIM_NEEDS_VERIFICATION,
    CLAIM_UNMAPPED,
    COMPOSE_FAILED,
    GENERATION_FAILED,
    MISSING_INPUT,
    NO_SPEC,
    PACKAGE_FAILED,
    PLAN_FAILED,
    PREFLIGHT_FAILED,
    PRESCREEN_REQUIRED,
    PROMPT_BUDGET_EXCEEDED,
    PROMPT_NOT_COMPILED,
    QA_FAILED,
    WORKFLOW_INCOMPATIBLE,
    ProviderError,
)
from .models import STAGE_ORDER, StageContext, StageResult, tail_lines

# H3 服务端 prompt 硬上限 / 安全线（2026-09-26 实测；与 make_15s / gen_one_take 同口径）
PROMPT_MAX = 10000
PROMPT_SAFE = 9800

GENERATE_TIMEOUT = 3600.0     # H3 一条 15s：实测 ~10 分钟，留足重试余量
COMPOSE_TIMEOUT = 7200.0      # 裁剪+转写+字幕+混音+归档


def _make_15s():
    """复用 make_15s 里已验证的门禁实现（口径唯一，不在这里重写一份）。"""
    import importlib
    return importlib.import_module("tools.make_15s")


def _spec_uid(ctx: StageContext) -> str:
    return ctx.uid


# ── 1. plan ────────────────────────────────────────────────────
def _spec_doc(spec_path: Path) -> dict:
    """读 spec JSON（读不到当空 dict，调用方各自决定怎么处理）。"""
    with suppress(OSError, ValueError):
        data = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    return {}


def _creative_artifacts(spec_path: Path) -> list[dict]:
    """spec 里 `creative.artifacts` 指向的研究依据 / CreativeDNA / 评分文件 → artifact 清单。

    这是"CreativeDNA、研究依据和筛选评分都能在 artifact/event 中追溯"的落地点：
    出片之后从 job 的 artifacts 就能直接翻到当初为什么选这个方案。
    """
    paths = (_spec_doc(spec_path).get("creative") or {}).get("artifacts") or {}
    out: list[dict] = []
    for type_, key in (("research", "research"), ("creative_dna", "dna"),
                       ("creative_scores", "scores"), ("claims", "claims"),
                       ("dialogue_check", "gate")):
        path = paths.get(key)
        if path and Path(path).is_file():
            out.append({"type": type_, "path": path})
    return out


_D_RE = re.compile(r"<d>\[([A-Za-z]+)\]\s*(.*?)\s*</d>", re.S)
_CAPTION_RE = re.compile(r'on-screen Chinese caption reads "([^"]*)"')


def _spoken_copy(prompt: str) -> list[str]:
    """从编译产物里只抽出**会给观众看到/听到**的中文：台词块 + 画面字幕。

    为什么不能整段扫：编译后的 prompt 是英文制作说明（`85mm 镜头`、`f/2`、
    `17k+5 帧`…），整段扫会把摄影参数当成产品参数报出来（Phase 7 集成实测的
    "85m 无法映射"就是 `85mm lens` 被截出来的）。合规门要扫的是**对外文案**。
    """
    out = [m.group(2) for m in _D_RE.finditer(prompt or "")]
    out += [m.group(1) for m in _CAPTION_RE.finditer(prompt or "")]
    return out


def _spec_claim_text(doc: dict) -> str:
    """spec 里所有"会对外出现"的文案（合规门只扫这些）。"""
    creative = doc.get("creative") or {}
    dna = creative.get("dna") or {}
    story = doc.get("story_spec") or {}
    chunks = [str(doc.get("title") or "")]
    for key in ("payoff", "ending", "CTA", "hook_type"):
        chunks.append(str(dna.get(key) or ""))
    chunks.extend(_spoken_copy(str(story.get("prompt") or "")))
    for line in (story.get("lines") or []):
        if isinstance(line, dict):
            chunks.append(str(line.get("text") or ""))
    for shot in (story.get("shots") or []):
        if isinstance(shot, dict):
            for key in ("line", "dialogue", "text", "beat"):
                chunks.append(str(shot.get(key) or ""))
    return "\n".join(c for c in chunks if c)


def _claims_gate(spec_path: Path, channel: str = "script") -> tuple[str, str, dict]:
    """Phase 6 合规门：数值/认证/质保/疗效/绝对化表述必须映射到**可用**的 claim。

    返回 (error_code, message, metrics)；error_code 为空表示通过。
    """
    from .. import claims as claims_mod

    doc = _spec_doc(spec_path)
    text = _spec_claim_text(doc)
    if not text:
        return "", "", {"claims_gate": "empty"}
    try:
        result = claims_mod.gate(text, channel)
    except claims_mod.RegistryError as exc:
        return (CLAIM_UNMAPPED, f"Claims Registry 不可用，无法完成合规校验：{exc}",
                {"claims_gate": "registry_error"})
    claim_ids = doc.get("claim_ids") or (doc.get("creative") or {}).get("claim_ids") or []
    metrics = {"claims_gate": "pass" if result.ok else "block",
               "claim_ids": result.claim_ids or list(claim_ids),
               "unmapped": len(result.unmapped), "blocked": len(result.blocked)}
    if result.ok:
        return "", "", metrics
    kinds = {f.kind for f in result.unmapped} | {f.kind for f in result.blocked}
    forbidden_hit = any("forbidden" in (f.blocked_reason or "") for f in result.blocked)
    if "forbidden_rewrite" in kinds or forbidden_hit:
        code = CLAIM_FORBIDDEN
    elif result.unmapped:
        code = CLAIM_UNMAPPED
    else:
        code = CLAIM_NEEDS_VERIFICATION
    return code, f"产品合规 Gate 不通过：{result.message()}", metrics


def _plan_for(ctx: StageContext):
    """跑一次自主规划（唯一实现是 lib.creative.CreativePlanner）。"""
    from ..creative import CreativePlanner
    planner = CreativePlanner(store=ctx.store, queue_dir=ctx.queue_dir, state_dir=ctx.state_dir)
    return planner.plan_for(ctx.uid, goal=ctx.config.goal)


def _spec_metrics(doc: dict) -> dict:
    """Phase 7：plan 阶段必须把"编译 + 路由"的结果报出来（可追溯、可断言）。"""
    story = doc.get("story_spec") or {}
    prompt = str(doc.get("prompt") or "")
    meta = doc.get("prompt_meta") or {}
    route = meta.get("route") or {}
    risk = meta.get("risk") or {}
    return {"plan_only": not bool(doc.get("prompt_ready")),
            "prompt_ready": bool(doc.get("prompt_ready")),
            "prompt_chars": len(prompt),
            "spec_version": str(doc.get("spec_version") or story.get("spec_version") or ""),
            "compiler_version": str(meta.get("compiler_version") or ""),
            "shot_count": len(story.get("shots") or []),
            "line_count": len(story.get("lines") or []),
            "workflow": str(doc.get("workflow") or ""),
            "workflow_source": str(doc.get("workflow_source") or ""),
            "fallback_workflows": list(doc.get("fallback_workflows") or []),
            "ref_images": len(doc.get("ref_images") or []),
            "ref_audios": len(doc.get("ref_audios") or []),
            "risk_level": str(risk.get("level") or ""),
            "route_reasons": len(route.get("reasons") or [])}


def stage_plan(ctx: StageContext) -> StageResult:
    spec_path = Path(ctx.spec) if ctx.spec else None
    if spec_path is not None and spec_path.is_file():
        doc = _spec_doc(spec_path)
        creative = doc.get("creative") or {}
        dna = creative.get("dna") or {}
        return StageResult.ok(
            "plan", artifacts=[{"type": "spec", "path": spec_path}] + _creative_artifacts(spec_path),
            metrics={"spec_bytes": spec_path.stat().st_size,
                     "structure": creative.get("structure", ""),
                     "genre": dna.get("genre", ""), "hook_type": dna.get("hook_type", ""),
                     "shot_pattern": dna.get("shot_pattern", ""),
                     "sales_point": dna.get("sales_point", ""),
                     **_spec_metrics(doc)},
            message=f"spec 就绪：{spec_path.name}",
            data={"dna": dna, "hotspot": creative.get("hotspot") or {}})
    if ctx.dry:
        return StageResult.ok("plan", artifacts=[{"type": "spec", "path": None,
                                                  "label": f"dry:{ctx.uid}"}],
                              metrics={"dry": True}, message="演练：虚拟 spec（不落盘）")
    # Phase 5：没有现成 spec → 系统自己选题（选题 → 研究依据 → CreativeDNA 候选 → 评分 → StorySpec）
    from ..creative.planner import PlannerError
    try:
        planned = _plan_for(ctx)
    except PlannerError as exc:
        return StageResult.fail("plan", PLAN_FAILED, f"自主规划失败：{exc}")
    except Exception as exc:
        return StageResult.fail("plan", PLAN_FAILED, f"自主规划异常：{type(exc).__name__}: {exc}")
    return StageResult.ok(
        "plan", artifacts=planned.artifacts(),
        metrics={"structure": planned.structure.get("name", ""),
                 "genre": planned.dna.genre, "hook_type": planned.dna.hook_type,
                 "shot_pattern": planned.dna.shot_pattern, "angle": planned.dna.angle,
                 "sales_point": planned.dna.sales_point,
                 "score_total": float(planned.scores.get("total") or 0.0),
                 "candidates": int((planned.decision or {}).get("candidate_count") or 0),
                 **_spec_metrics(_spec_doc(planned.spec_path) if planned.spec_path else {})},
        message=f"自主规划完成：{planned.message}",
        data={"dna": planned.dna.to_dict(), "hotspot": planned.hotspot,
              "shortlist": planned.shortlist, "decision": planned.decision.get("rule", "")})


# ── 2. preflight ───────────────────────────────────────────────
def _static_dialogue_gate(ctx: StageContext, uid: str, doc: dict) -> tuple[bool, str, dict]:
    """静态对白门禁（tools/check_dialogue.mjs）——编译产物也要过同一道闸。

    Phase 7 起这不是"只有人工稿才跑"的可选项：编译出的 prompt 会被包上
    `duration="N"` 再送进门禁，于是 R10/R28 的语速预算对**任何镜数/句数**都真的生效
    （旧路径里 payload 不带 duration，这两条一直被跳过）。
    R26 的阈值也同步改成 H3 服务端实测的 10000 字符。
    """
    import subprocess

    prompt = str(doc.get("prompt") or "")
    metrics: dict = {"dialogue_gate_ok": None}
    if not prompt:
        return True, "", metrics
    gate = ctx.workspace / f"gate_{uid}.txt"
    try:
        from ..creative.compiler import gate_text
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text(gate_text(prompt, duration=int(doc.get("duration") or 15),
                                  resolution=str(doc.get("resolution") or "768p竖")),
                        encoding="utf-8")
    except Exception as exc:      # noqa: BLE001 —— 写不出检查文件不该拦出片
        metrics["dialogue_gate_ok"] = None
        return True, f"静态门禁 payload 写入失败（跳过）：{exc}", metrics

    script = Path(__file__).resolve().parents[2] / "tools" / "check_dialogue.mjs"
    if not script.is_file():
        return True, "未找到 tools/check_dialogue.mjs（跳过静态门禁）", metrics
    try:
        proc = subprocess.run(["node", str(script), str(gate)], capture_output=True,
                              text=True, errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"node 不可用（跳过静态门禁）：{exc}", metrics
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    ok = "0 ERROR" in out
    metrics["dialogue_gate_ok"] = bool(ok)
    metrics["dialogue_gate_iterations"] = 1
    return ok, out.replace("\n", " | "), metrics


def _spec_lines(doc: dict) -> list[dict]:
    rows = (doc.get("story_spec") or {}).get("lines") or doc.get("lines") or []
    return [r for r in rows if isinstance(r, dict) and str(r.get("text") or "").strip()]


def _workflow_gate(doc: dict) -> tuple[str, str, dict]:
    """链条能力校验：router 选的链必须真的装得下这条 spec（任务 9）。"""
    from ..creative.workflow import WorkflowIncompatible, requirements_from_spec, validate_chain

    chain = [str(doc.get("workflow") or "")] + [str(w) for w in (doc.get("fallback_workflows") or [])]
    chain = [w for w in chain if w]
    if not chain:
        return WORKFLOW_INCOMPATIBLE, "spec 没有指定任何工作流 → 拒绝提交", {"workflow_gate": "empty"}
    req = requirements_from_spec(doc)
    if req.audio and not doc.get("ref_audios"):
        # 有台词的片没有音色参考 = 每次生成换一把声音，先拦住
        return (MISSING_INPUT, "有对白却没有 ref_audios（音色锁定缺失）→ 拒绝付费提交",
                {"workflow_gate": "no_voice"})
    bad = validate_chain(chain, req)
    metrics = {"workflow_gate": "pass" if not bad else "block",
               "workflow": chain[0], "fallbacks": chain[1:],
               "requirement": req.to_dict()}
    if not bad:
        return "", "", metrics
    try:      # 交给 router 复核：是真的一条都装不下，还是只是这条链写错了
        from ..creative.workflow import choose
        choose(req)
    except WorkflowIncompatible as exc:
        return (WORKFLOW_INCOMPATIBLE,
                f"没有工作流能保住全部关键能力（时长/参考图/音频）：{exc.message}", metrics)
    except Exception:      # noqa: BLE001 —— router 复核不了就按链本身的结论走
        pass
    return (WORKFLOW_INCOMPATIBLE,
            "工作流链含不兼容项（会静默丢掉音频/参考图/时长）："
            + "；".join(f"{b['workflow']}: {b['reason']}" for b in bad), metrics)


def _prescreen_gate(ctx: StageContext, uid: str, doc: dict) -> tuple[str, str, dict]:
    """高风险新构图必须先过 5s 预筛（任务 11/12）；低风险直接放行。"""
    from ..creative.prescreen import PRESCREEN_SECONDS, needs_prescreen, prescreen_passed, risk_of

    risk = risk_of(doc)
    metrics = {"risk_level": risk["level"], "risk_score": risk["score"],
               "risk_reasons": len(risk["reasons"]), "prescreen": None}
    if not needs_prescreen(doc):
        metrics["prescreen"] = "not_required"
        return "", "", metrics
    metrics["prescreen_seconds"] = PRESCREEN_SECONDS
    if prescreen_passed(ctx.store, uid):
        metrics["prescreen"] = "passed"
        return "", "", metrics
    metrics["prescreen"] = "required"
    return (PRESCREEN_REQUIRED,
            f"高风险新构图（{metrics['risk_level']} {metrics['risk_score']}）："
            f"先跑 {PRESCREEN_SECONDS}s 预筛并留下 passed 结论，才允许跑 15s 正式片", metrics)


def stage_preflight(ctx: StageContext) -> StageResult:
    if ctx.dry:
        return StageResult.ok("preflight", metrics={"dry": True}, message="演练：跳过门禁")

    metrics: dict = {}
    problems: list[str] = []

    if ctx.spec is not None and Path(ctx.spec).is_file():
        doc = _spec_doc(Path(ctx.spec))
        # Phase 7 边界：StorySpec 就绪但没编译出 prompt 时绝不放行到付费生成
        # （编译成功后 plan_only=False，这道闸自动解开）。
        if not doc.get("prompt_ready") or not str(doc.get("prompt") or "").strip():
            return StageResult.fail(
                "preflight", PROMPT_NOT_COMPILED,
                "StorySpec 已就绪，但 H3 提示词尚未编译（PromptCompiler 未产出 prompt）——"
                "为不浪费付费额度，本次不进入生成。",
                metrics={"plan_only": True, "prompt_ready": bool(doc.get("prompt_ready"))})
        # Phase 6 合规门：文案里的产品承诺必须映射到可用 claim，否则绝不放行到付费生成
        code, claim_msg, claim_metrics = _claims_gate(Path(ctx.spec))
        if code:
            return StageResult.fail("preflight", code, claim_msg, metrics=claim_metrics)
        metrics.update(claim_metrics)

        # Phase 7 ①：prompt 预算（编译期已算过，这里用服务端口径复核一遍）
        n_prompt = len(str(doc.get("prompt") or ""))
        metrics["prompt_chars"] = n_prompt
        if n_prompt > PROMPT_MAX:
            return StageResult.fail("preflight", PROMPT_BUDGET_EXCEEDED,
                                    f"prompt {n_prompt} 字符 > H3 上限 {PROMPT_MAX} → 付费前阻断",
                                    metrics=metrics)
        if n_prompt > PROMPT_SAFE:
            problems.append(f"prompt {n_prompt}/{PROMPT_MAX} 字符超安全线 → 先压缩再出片")

        # Phase 7 ②：工作流链必须保住音频/参考图/时长（不兼容就拒绝提交）
        code, wf_msg, wf_metrics = _workflow_gate(doc)
        metrics.update(wf_metrics)
        if code:
            return StageResult.fail("preflight", code, wf_msg, metrics=metrics)

        # Phase 7 ③：高风险新构图先预筛（低风险直接过）
        code, ps_msg, ps_metrics = _prescreen_gate(ctx, _spec_uid(ctx), doc)
        metrics.update(ps_metrics)
        if code:
            return StageResult.fail("preflight", code, ps_msg, metrics=metrics)

        # Phase 7 ④：静态对白门禁（同一条闸，任何镜数/句数都适用）
        ok_gate, gate_msg, gate_metrics = _static_dialogue_gate(ctx, _spec_uid(ctx), doc)
        metrics.update(gate_metrics)
        if not ok_gate:
            return StageResult.fail("preflight", PREFLIGHT_FAILED,
                                    f"静态对白门禁未过（要求 0 ERROR）：{gate_msg}",
                                    metrics=metrics)

        # Phase 7 ⑤：要说话的片必须有词 —— spec.lines 或旧口径台词文件二选一
        from ..creative.compiler import needs_dialogue
        mode = str((doc.get("creative") or {}).get("dna", {}).get("dialogue_mode") or "")
        has_lines = bool(_spec_lines(doc))
        legacy_lines = (ctx.root / "docs" / f"onetake_lines_{_spec_uid(ctx)}.txt").is_file()
        metrics["dialogue_authored"] = bool(has_lines or legacy_lines)
        if needs_dialogue(mode) and not (has_lines or legacy_lines):
            return StageResult.fail(
                "preflight", MISSING_INPUT,
                f"台词模式「{mode}」必须有成句台词：spec.story_spec.lines 为空且没有 "
                f"docs/onetake_lines_{_spec_uid(ctx)}.txt → 拒绝付费出一条没词的片",
                metrics=metrics)

        if not problems:
            return StageResult.ok("preflight", metrics=metrics,
                                  message=f"门禁通过：{metrics}")
        message = " ｜ ".join(problems)
        if ctx.force:
            return StageResult.ok("preflight", metrics={**metrics, "forced": True},
                                  message=f"预检未过但 --force 强制继续：{message}")
        return StageResult.fail("preflight", PREFLIGHT_FAILED, message, metrics=metrics)

    # ── 旧口径兜底（没有 spec 文件：只看台词文件）───────────────
    uid = _spec_uid(ctx)
    try:
        lines_ok, lines_msg = _make_15s().assert_lines(uid)
    except FileNotFoundError:
        return StageResult.fail(
            "preflight", MISSING_INPUT,
            f"缺少台词文件 docs/onetake_lines_{uid}.txt（spec 未配套生成）")
    metrics["lines_ok"] = bool(lines_ok)
    if not lines_ok:
        problems.append(lines_msg)
    if not problems:
        return StageResult.ok("preflight", metrics=metrics, message="门禁通过（旧口径：台词文件）")
    message = " ｜ ".join(problems)
    if ctx.force:
        return StageResult.ok("preflight", metrics={**metrics, "forced": True},
                              message=f"预检未过但 --force 强制继续：{message}")
    return StageResult.fail("preflight", PREFLIGHT_FAILED, message, metrics=metrics)


# ── 3. generate ────────────────────────────────────────────────
def stage_generate(ctx: StageContext) -> StageResult:
    out = ctx.workspace / "onetake.mp4"
    if ctx.dry:
        return StageResult.ok("generate", metrics={"dry": True, "cost": 0.0},
                              message="演练：不提交生成")
    if out.is_file() and out.stat().st_size > 0 and not ctx.force:
        return StageResult.ok("generate", artifacts=[{"type": "video", "path": out}],
                              metrics={"skipped": True}, message="已有 onetake.mp4，跳过生成")
    if ctx.spec is None:
        return StageResult.fail("generate", NO_SPEC, "缺少 spec，无法提交生成")
    try:
        spec = json.loads(Path(ctx.spec).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return StageResult.fail("generate", MISSING_INPUT, f"spec 无法解析：{exc}")

    try:
        outcome = _generator(ctx).generate(
            uid=ctx.uid, prompt=str(spec.get("prompt") or ""),
            duration=int(spec.get("duration") or 15),
            resolution=str(spec.get("resolution") or "768p竖"),
            workflow=str(spec.get("workflow") or "multi_image_15s"),
            fallback_workflows=spec.get("fallback_workflows") or [],
            ref_images=spec.get("ref_images") or [],
            ref_audios=spec.get("ref_audios") or [],
            out_path=out)
    except ProviderError as exc:
        return StageResult.fail("generate", exc.error_code,
                                f"生成失败：{exc.message}", data=exc.data)

    if not out.is_file() or out.stat().st_size == 0:
        return StageResult.fail("generate", GENERATION_FAILED, f"生成产物缺失：{out}")

    # 落快照：与 gen_one_take 同口径（onetake_task.json / onetake_result.json）
    _write_json(ctx.workspace / "onetake_task.json",
                {"task_id": outcome.task_id, "workflow": outcome.workflow,
                 "spec": str(ctx.spec), "resumed": outcome.reused})
    _write_json(ctx.workspace / "onetake_result.json",
                {"task_id": outcome.task_id, "workflow": outcome.workflow,
                 "video_path": str(out), "duration": spec.get("duration"),
                 "cost_est": outcome.cost, "resumed": outcome.reused})

    metrics = {"bytes": out.stat().st_size, "cost": outcome.cost,
               "task_id": outcome.task_id, "workflow": outcome.workflow,
               "reused": outcome.reused, "compressed": outcome.compressed,
               "prompt_chars": outcome.prompt_chars}
    return StageResult.ok("generate", artifacts=[{"type": "video", "path": out}],
                          metrics=metrics,
                          message=(("复用已提交任务 " if outcome.reused else "H3 生成完成 ")
                                   + f"{outcome.workflow}（¥{outcome.cost:.2f}）"),
                          data={"fingerprint": outcome.fingerprint})


def _provider_for(ctx: StageContext):
    if ctx.provider is not None:
        return ctx.provider
    from .providers import AutoDLProvider
    return AutoDLProvider()


def _generator(ctx: StageContext):
    from .generation import IdempotentGenerator
    return IdempotentGenerator(ctx.store, _provider_for(ctx), root=ctx.root, log=ctx.say,
                               sleep=ctx.sleep, poll_interval=ctx.poll_interval,
                               max_wait=ctx.max_wait,
                               download_retries=ctx.download_retries,
                               cancel_event=ctx.cancel_event)


def _write_json(path: Path, data: dict) -> None:
    with suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _generation_cost(ctx: StageContext) -> float:
    """成本取生成器写回的 onetake_result.json；没有就按 768p 单价估算。"""
    result_file = ctx.workspace / "onetake_result.json"
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        return float(data.get("cost_est") or 0.0)
    except (OSError, ValueError, TypeError):
        return 0.9


# ── 4. qa ──────────────────────────────────────────────────────
def _qa_gate(ctx: StageContext, *, phase: str, stage: str) -> StageResult:
    """自动验片（Phase 8）：Critic 判定 → 落 artifact → 写 evaluation → 带主错误码失败。

    失败时把 `findings` 放进 `data`；`service` 的修复环据此生成 RepairPlan
    （回退 generate 重生 / compose 重建字幕），次数受 `cfg.max_repairs` 限制。
    没有证据的维度记 `skipped`（不算通过），并在报告里写明 —— 绝不假装验过。
    """
    from ..qa import critic as qa_critic

    doc = _spec_doc(ctx.spec) if ctx.spec is not None else {}
    report = qa_critic.critique(ctx.workspace, ctx.uid, doc, phase=phase, stage=stage)

    out_dir = ctx.workspace / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"qa_report_{phase}.json"
    md_path = out_dir / f"qa_report_{phase}.md"
    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    artifacts = [{"type": "qa_report", "path": json_path},
                 {"type": "qa_report_md", "path": md_path}]

    if ctx.store is not None:
        for dim, status in report.dimensions.items():
            ctx.store.add_evaluation(
                ctx.uid, f"qa_{dim}", stage=stage,
                passed=None if status == "skipped" else status == "pass",
                detail={"phase": phase, "status": status, "coverage": report.coverage,
                        "codes": sorted({f.error_code for f in report.findings
                                         if f.dimension == dim})})
        ctx.store.add_evaluation(ctx.uid, f"qa_report_{phase}", stage=stage,
                                 score=report.score(), passed=report.passed,
                                 detail=report.to_dict())

    metrics = {"qa_phase": phase, "qa_passed": report.passed, "qa_score": report.score(),
               "qa_coverage": report.coverage, "qa_codes": report.codes(),
               "qa_dimensions": report.dimensions}
    if not report.failed:
        return StageResult.ok(stage, artifacts=artifacts, metrics=metrics,
                              message=f"验片通过：{report.summary()}")
    top = "；".join(f"[{f.severity}] {f.dimension}/{f.error_code}: {f.message}"
                    for f in report.findings[:4])
    return StageResult.fail(stage, report.primary_error() or QA_FAILED,
                            f"验片不通过（{report.summary()}）：{top}",
                            metrics=metrics, artifacts=artifacts,
                            data={"findings": [f.to_dict() for f in report.findings],
                                  "qa_report": str(json_path), "phase": phase})


def stage_qa(ctx: StageContext) -> StageResult:
    out = ctx.workspace / "onetake.mp4"
    if ctx.dry:
        return StageResult.ok("qa", metrics={"dry": True}, message="演练：跳过验片")
    if not out.is_file():
        return StageResult.fail("qa", QA_FAILED, f"成片不存在：{out}")
    res = _qa_gate(ctx, phase="gen", stage="qa")
    if res.success:
        res.artifacts.append({"type": "video", "path": out})
    return res


# ── 5. compose ─────────────────────────────────────────────────
def stage_compose(ctx: StageContext) -> StageResult:
    if ctx.dry:
        return StageResult.ok("compose", metrics={"dry": True}, message="演练：跳过后期")
    if ctx.spec is None:
        return StageResult.fail("compose", NO_SPEC, "缺少 spec，无法进入后期合成")

    cmd = [ctx.python, ctx.root / "tools" / "make_15s.py", "run", str(ctx.spec), "--skip-gen"]
    if ctx.force:
        cmd.append("--force")
    res = ctx.run_subprocess(cmd, timeout=COMPOSE_TIMEOUT)
    final = ctx.workspace / "onetake_final.mp4"
    tail = tail_lines(res.stdout or "")
    if res.returncode != 0 or not final.is_file():
        return StageResult.fail(
            "compose", COMPOSE_FAILED,
            f"后期合成失败：returncode={res.returncode}",
            metrics={"returncode": res.returncode}, data={"tail": tail})

    gate = _qa_gate(ctx, phase="final", stage="compose")
    artifacts = [{"type": "final", "path": final}, *gate.artifacts]
    metrics = {"bytes": final.stat().st_size, **gate.metrics}
    if not gate.success:
        return StageResult.fail("compose", gate.error_code or QA_FAILED, gate.message,
                                metrics=metrics, artifacts=artifacts, data=gate.data)
    return StageResult.ok("compose", artifacts=artifacts, metrics=metrics,
                          message="后期合成完成（剪切/字幕/BGM/音效/归档）",
                          data={"tail": tail})


def stage_package(ctx: StageContext) -> StageResult:
    final = ctx.workspace / "onetake_final.mp4"
    if ctx.dry:
        return StageResult.ok("package", metrics={"dry": True}, message="演练：跳过归档核对")
    if not final.is_file():
        return StageResult.fail("package", PACKAGE_FAILED, f"成片不存在，无法归档：{final}")

    artifacts = [{"type": "final", "path": final}]
    metrics = {"bytes": final.stat().st_size}
    title = ""
    if ctx.spec is not None:
        try:
            title = str(json.loads(Path(ctx.spec).read_text(encoding="utf-8")).get("title") or "")
        except (OSError, ValueError):
            title = ""
    approved_dir = ctx.root / "out" / "approved"
    archive = None
    if title and approved_dir.is_dir():
        hits = sorted(approved_dir.glob(f"{title}_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        archive = hits[0] if hits else None
    metrics["archive_present"] = bool(archive)
    if archive is not None:
        artifacts.append({"type": "archive", "path": archive})
    return StageResult.ok("package", artifacts=artifacts, metrics=metrics,
                          message="已归档" + (f"：{archive.name}" if archive else "（未找到归档件，需人工确认）"))


BUILTIN_STAGES = {
    "plan": stage_plan,
    "preflight": stage_preflight,
    "generate": stage_generate,
    "qa": stage_qa,
    "compose": stage_compose,
    "package": stage_package,
}


def default_stages() -> dict:
    """默认阶段实现（测试可注入同名假实现替换）。"""
    return dict(BUILTIN_STAGES)


def resolve_stages(names: tuple[str, ...] | list[str] | None = None) -> tuple[str, ...]:
    chosen = [s for s in STAGE_ORDER if s in set(names or STAGE_ORDER)]
    return tuple(chosen or STAGE_ORDER)
