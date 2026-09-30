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
from contextlib import suppress
from pathlib import Path

from .errors import (
    COMPOSE_FAILED,
    GENERATION_FAILED,
    MISSING_INPUT,
    NO_SPEC,
    PACKAGE_FAILED,
    PREFLIGHT_FAILED,
    QA_FAILED,
    ProviderError,
)
from .models import STAGE_ORDER, StageContext, StageResult, tail_lines

# H3 服务端 prompt 硬上限 / 安全线（2026-09-26 实测；与 make_15s / gen_one_take 同口径）
PROMPT_MAX = 10000
PROMPT_SAFE = 9800

GENERATE_TIMEOUT = 3600.0     # H3 一条 15s：实测 ~10 分钟，留足重试余量
COMPOSE_TIMEOUT = 7200.0      # 裁剪+转写+字幕+混音+归档
MIN_FINAL_BYTES = 100_000     # 低于此值视为坏文件（15s 成片实测 >1MB）


def _make_15s():
    """复用 make_15s 里已验证的门禁实现（口径唯一，不在这里重写一份）。"""
    import importlib
    return importlib.import_module("tools.make_15s")


def _spec_uid(ctx: StageContext) -> str:
    return ctx.uid


# ── 1. plan ────────────────────────────────────────────────────
def stage_plan(ctx: StageContext) -> StageResult:
    if ctx.spec is not None and Path(ctx.spec).is_file():
        return StageResult.ok(
            "plan", artifacts=[{"type": "spec", "path": ctx.spec}],
            metrics={"spec_bytes": Path(ctx.spec).stat().st_size},
            message=f"spec 就绪：{Path(ctx.spec).name}")
    if ctx.dry:
        return StageResult.ok("plan", artifacts=[{"type": "spec", "path": None,
                                                  "label": f"dry:{ctx.uid}"}],
                              metrics={"dry": True}, message="演练：虚拟 spec（不落盘）")
    return StageResult.fail(
        "plan", NO_SPEC,
        "没有可执行的 spec：把 spec 放进 state/queue_15s/ 或调用 start(goal=...) 指定选题")


# ── 2. preflight ───────────────────────────────────────────────
def stage_preflight(ctx: StageContext) -> StageResult:
    if ctx.dry:
        return StageResult.ok("preflight", metrics={"dry": True}, message="演练：跳过门禁")

    metrics: dict = {}
    problems: list[str] = []

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

    if ctx.spec is not None:
        try:
            spec = json.loads(Path(ctx.spec).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return StageResult.fail("preflight", MISSING_INPUT, f"spec 无法解析：{exc}")
        n_prompt = len(str(spec.get("prompt", "")))
        metrics["prompt_chars"] = n_prompt
        if n_prompt > PROMPT_SAFE:
            problems.append(f"prompt {n_prompt}/{PROMPT_MAX} 字符超安全线 → 先压缩再出片"
                            "（H3 会拒收，白等）")

        check_file = ctx.root / "docs" / f"onetake_check_{uid}.txt"
        if check_file.is_file():
            ok_gate, gate_msg = _make_15s().check_dialogue(Path(ctx.spec))
            metrics["dialogue_gate_ok"] = bool(ok_gate)
            if not ok_gate:
                problems.append(f"对白门禁未过（要求 0 ERROR）：{gate_msg}")
        else:
            metrics["dialogue_gate_ok"] = None

    if not problems:
        return StageResult.ok("preflight", metrics=metrics,
                              message="门禁通过" + (f"：{metrics}" if metrics else ""))
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
def stage_qa(ctx: StageContext) -> StageResult:
    out = ctx.workspace / "onetake.mp4"
    if ctx.dry:
        return StageResult.ok("qa", metrics={"dry": True}, message="演练：跳过验片")
    if not out.is_file():
        return StageResult.fail("qa", QA_FAILED, f"成片不存在：{out}")
    size = out.stat().st_size
    if size < MIN_FINAL_BYTES:
        return StageResult.fail("qa", QA_FAILED, f"成片疑似损坏（{size} 字节 < {MIN_FINAL_BYTES}）",
                                metrics={"bytes": size})
    metrics = {"bytes": size}
    try:
        from lib.tools import get_video_duration
        metrics["duration"] = round(get_video_duration(str(out)), 2)
    except Exception:  # ffprobe 不可用不应阻断出片，只少一个指标
        metrics["duration"] = None
    if ctx.store is not None:
        ctx.store.add_evaluation(ctx.uid, "qa_basic", stage="qa",
                                 passed=True, detail={"bytes": size,
                                                      "duration": metrics["duration"]})
    return StageResult.ok("qa", artifacts=[{"type": "video", "path": out}],
                          metrics=metrics, message="验片通过")


# ── 5. compose ─────────────────────────────────────────────────
def stage_compose(ctx: StageContext) -> StageResult:
    if ctx.dry:
        return StageResult.ok("compose", metrics={"dry": True}, message="演练：跳过后期")
    if ctx.spec is None:
        return StageResult.fail("compose", NO_SPEC, "缺少 spec，无法后期合成")

    cmd = [ctx.python, ctx.root / "tools" / "make_15s.py", "run", str(ctx.spec), "--skip-gen"]
    if ctx.force:
        cmd.append("--force")
    res = ctx.run_subprocess(cmd, timeout=COMPOSE_TIMEOUT)
    final = ctx.workspace / "onetake_final.mp4"
    tail = tail_lines(res.stdout or "")
    if res.returncode != 0 or not final.is_file():
        return StageResult.fail(
            "compose", COMPOSE_FAILED,
            f"后期合成失败（returncode={res.returncode}）",
            metrics={"returncode": res.returncode}, data={"tail": tail})
    return StageResult.ok("compose", artifacts=[{"type": "final", "path": final}],
                          metrics={"bytes": final.stat().st_size},
                          message="后期合成完成（裁剪/字幕/BGM/音效/归档）",
                          data={"tail": tail})


# ── 6. package ─────────────────────────────────────────────────
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
