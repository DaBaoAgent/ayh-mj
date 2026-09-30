"""幂等生成驱动（Phase 4 核心）。

把"提交 → 落 DB → 轮询 → 下载"做成一条**可中断、可重启、不重复扣费**的流水线：

  必做 1  提交前算 fingerprint（job+stage+prompt+refs+workflow）；
  必做 2  拿到 task_id **立即** upsert 进 provider_tasks，然后才进入轮询；
  必做 3  进程恢复时：fingerprint 命中已有 task_id → 只 query，禁止重新 create_task；
  必做 4  供应商 SUCCESS 但下载失败 → 只重下（绝不重生成）；
  必做 5  瞬时网络错误指数退避；业务错误不在此处无限循环；
  必做 6  prompt 超限在**付费前**压缩/阻断（AutoDL 提交数 = 0）。

本模块与 `s4_generate/gen_one_take.py` 共用同一套实现（后者是薄 CLI 包装）。
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from .errors import (
    DOWNLOAD_FAILED,
    PROMPT_TOO_LONG,
    DownloadFailed,
    GenerationFailed,
    GenerationTimeout,
    NetworkTransient,
    PromptTooLong,
    ProviderError,
    ProviderRejected,
    backoff_delay,
    is_transient,
)
from .errors import (
    GENERATION_TIMEOUT as _GEN_TIMEOUT,
)
from .idempotency import fingerprint, fingerprint_parts
from .providers import ProviderAdapter, ProviderTask

# H3 服务端 prompt 硬上限 / 安全线（2026-09-26 实测；与 make_15s / gen_one_take 同口径）
PROMPT_MAX = 10000
PROMPT_SAFE = 9800

PRICE_PER_SEC_BY_RES = {"480p": 0.04, "768p": 0.06, "1080p": 0.10}


def cost_for(duration: int, resolution: str) -> float:
    key = resolution[:resolution.index("p") + 1] if "p" in resolution else "768p"
    return round(PRICE_PER_SEC_BY_RES.get(key, 0.06) * int(duration), 3)


def compress_prompt(text: str, *, limit: int = PROMPT_MAX) -> tuple[str, bool]:
    """确定性压缩：删重复约束行 + 压空白，**不删镜头/不改台词**。"""
    original = text or ""
    seen: set[str] = set()
    kept: list[str] = []
    for line in original.splitlines():
        key = re.sub(r"\s+", " ", line).strip()
        if key and key in seen:
            continue                     # 完全重复的约束行只留第一处
        if key:
            seen.add(key)
        kept.append(re.sub(r"[ \t]+", " ", line).rstrip())
    out: list[str] = []
    blanks = 0
    for line in kept:
        if not line.strip():
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        out.append(line)
    compressed = "\n".join(out).strip()
    return compressed, compressed != original.strip()


def ensure_prompt_budget(prompt: str, *, limit: int = PROMPT_MAX,
                         safe: int = PROMPT_SAFE) -> tuple[str, dict]:
    """付费前把 prompt 压到安全线内；压不下来就抛 PromptTooLong（0 提交、0 花费）。"""
    text = prompt or ""
    meta = {"prompt_chars": len(text), "limit": limit, "safe": safe, "compressed": False}
    if len(text) > safe:
        smaller, changed = compress_prompt(text, limit=limit)
        if changed and len(smaller) < len(text):
            text, meta["compressed"] = smaller, True
            meta["prompt_chars_after_compress"] = len(smaller)
    if len(text) > limit:
        raise PromptTooLong(
            f"prompt {len(text)} 字符 > 上限 {limit}；压缩后仍超限 → 付费前阻断"
            f"（未提交、0 元）",
            data={**meta, "prompt_chars_final": len(text), "error_code": PROMPT_TOO_LONG})
    meta["prompt_chars_final"] = len(text)
    return text, meta


@dataclass
class GenerationOutcome:
    """一次幂等生成的结果。"""

    video_path: Path
    task_id: str
    workflow: str
    cost: float
    fingerprint: str
    prompt_chars: int
    compressed: bool = False
    reused: bool = False
    download_attempts: int = 1
    poll_queries: int = 0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"video_path": str(self.video_path), "task_id": self.task_id,
                "workflow": self.workflow, "cost": self.cost,
                "fingerprint": self.fingerprint, "prompt_chars": self.prompt_chars,
                "compressed": self.compressed, "reused": self.reused,
                "download_attempts": self.download_attempts,
                "poll_queries": self.poll_queries}


class IdempotentGenerator:
    """幂等生成驱动（store + provider 注入，测试可完全离线）。"""

    def __init__(self, store, provider: ProviderAdapter, *, root: Path | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] | None = None,
                 poll_interval: float = 20.0, max_wait: float = 1800.0,
                 download_retries: int = 3, stage: str = "generate",
                 cancel_event=None) -> None:
        self.store = store
        self.provider = provider
        self.root = Path(root) if root else Path.cwd()
        self.sleep = sleep
        self.log = log
        self.poll_interval = poll_interval
        self.max_wait = max_wait
        self.download_retries = download_retries
        self.stage = stage
        self.cancel_event = cancel_event

    # ── 主流程 ────────────────────────────────────────────────
    def generate(self, *, uid: str, prompt: str, duration: int, resolution: str,
                 workflow: str, fallback_workflows: Iterable[str] = (), ref_images=(),
                 ref_audios=(), out_path: Path | str,
                 payload_factory: Callable[[str], dict] | None = None) -> GenerationOutcome:
        prompt, meta = ensure_prompt_budget(prompt)          # 付费前门禁（0 提交）
        refs = [*ref_images, *ref_audios]
        chain = _workflow_chain(workflow, fallback_workflows)
        out_path = Path(out_path)
        cost = cost_for(duration, resolution)
        last_error: ProviderError | None = None

        for wf in chain:
            if self._cancelled():
                raise NetworkTransient("收到取消请求，停止生成")
            fp = fingerprint(job_uid=uid, stage=self.stage, prompt=prompt, refs=refs,
                             workflow=wf, root=self.root)
            row = self.store.find_provider_task(uid, fp)
            reused = bool(row and row.get("task_id"))
            if reused:
                task_id = str(row["task_id"])
                self._event(uid, "provider_reused",
                            f"复用已提交任务 {task_id}（{wf}）：只查询，不重新提交",
                            {"fingerprint": fp, "task_id": task_id, "workflow": wf})
                if self._already_downloaded(row, out_path):
                    self.store.finish_provider_task(uid, fp, status="DONE",
                                                    output_path=str(out_path), cost=cost)
                    return self._outcome(out_path, task_id, wf, fp, prompt, meta, cost,
                                         reused=True, download_attempts=0)
                try:
                    task = self.provider.query(task_id)
                except ProviderError as exc:
                    last_error = exc
                    self._event(uid, "provider_query_failed", str(exc.message),
                                {"fingerprint": fp, "error_code": exc.error_code}, "warning")
                    continue
                self.store.upsert_provider_task(
                    uid, fp, stage=self.stage, provider=self.provider.name, workflow=wf,
                    task_id=task_id, status=task.status, bump_attempts=True)
            else:
                payload = (payload_factory or (lambda w: _default_payload(
                    prompt=prompt, duration=duration, resolution=resolution,
                    ref_images=ref_images, ref_audios=ref_audios, root=self.root)))(wf)
                try:
                    task = self.provider.submit(payload=payload, workflow=wf)
                except ProviderError as exc:
                    last_error = exc
                    self._event(uid, "provider_rejected",
                                f"提交 {wf} 失败（{exc.error_code}）：{exc.message}",
                                {"workflow": wf, "error_code": exc.error_code}, "warning")
                    continue                     # 换兼容 workflow 再试（RepairEngine: SWITCH_WORKFLOW）
                # 必做 2：拿到 task_id 立即落 DB（轮询之前）
                self.store.upsert_provider_task(
                    uid, fp, stage=self.stage, provider=self.provider.name, workflow=wf,
                    task_id=task.task_id, status="SUBMITTED")
                task_id = task.task_id
                self._event(uid, "provider_submitted",
                            f"已提交 {wf}：task_id={task_id}（prompt {len(prompt)} 字符）",
                            {**fingerprint_parts(job_uid=uid, stage=self.stage, prompt=prompt,
                                                 refs=refs, workflow=wf, root=self.root),
                             "task_id": task_id, "workflow": wf})

            try:
                task = self._poll(uid, fp, task)
            except ProviderError as exc:
                last_error = exc
                self._event(uid, "provider_failed", f"{wf}：{exc.message}",
                            {"fingerprint": fp, "error_code": exc.error_code}, "warning")
                continue

            if task.failed or not task.succeeded:
                last_error = (GenerationTimeout(f"{wf} 未在 {self.max_wait:.0f}s 内完成")
                              if not task.failed else
                              ProviderRejected(f"{wf} 供应商返回失败：{task.status}"))
                self.store.finish_provider_task(uid, fp, status="FAILED",
                                                error_code=last_error.error_code)
                self._event(uid, "provider_failed", f"{wf}：{last_error.message}",
                            {"fingerprint": fp, "error_code": last_error.error_code}, "warning")
                continue

            try:
                path, attempts = self._download(uid, fp, task, out_path)
            except DownloadFailed as exc:
                last_error = exc
                self.store.finish_provider_task(uid, fp, status="FAILED",
                                                result_url=task.url,
                                                error_code=DOWNLOAD_FAILED)
                self._event(uid, "download_failed",
                            f"{wf} 已成功但下载失败（{self.download_retries + 1} 次）："
                            f"{exc.message}",
                            {"fingerprint": fp, "task_id": task_id,
                             "error_code": DOWNLOAD_FAILED}, "warning")
                continue
            self.store.finish_provider_task(uid, fp, status="DONE", result_url=task.url,
                                            output_path=str(path),
                                            cost=cost)
            return self._outcome(out_path, task_id, wf, fp, prompt, meta, cost,
                                 reused=reused, download_attempts=attempts)

        raise last_error or GenerationFailed("全部工作流失败（无可用提交）")

    # ── 轮询 ──────────────────────────────────────────────────
    def _poll(self, uid: str, fp: str, task: ProviderTask) -> ProviderTask:
        if task.succeeded or task.failed:
            return task
        waited = 0.0
        query = 0
        while waited < self.max_wait:
            if self._cancelled():
                raise NetworkTransient("收到取消请求，停止轮询")
            self.sleep(self.poll_interval)
            waited += self.poll_interval
            try:
                task = self.provider.query(task.task_id)
            except ProviderError as exc:
                if is_transient(exc.error_code) and waited < self.max_wait:
                    query += 1
                    continue                       # 瞬时错误：退避后继续轮询（不算失败）
                raise
            query += 1
            self.store.upsert_provider_task(uid, fp, stage=self.stage,
                                            provider=self.provider.name,
                                            workflow=task.workflow or "",
                                            task_id=task.task_id, status=task.status)
            if task.succeeded or task.failed:
                return task
        raise GenerationTimeout(f"等待超时（{self.max_wait / 60:.0f} 分钟）：{task.task_id}",
                                data={"error_code": _GEN_TIMEOUT})

    # ── 下载（只重下，绝不重生成）────────────────────────────
    def _download(self, uid: str, fp: str, task: ProviderTask, out_path: Path):
        self.store.finish_provider_task(uid, fp, status="DOWNLOADING",
                                        result_url=task.url)
        attempts = 0
        while True:
            attempts += 1
            if self._cancelled():
                raise NetworkTransient("收到取消请求，停止下载")
            try:
                path = Path(self.provider.download(task, str(out_path)))
                if not path.is_file() or path.stat().st_size == 0:
                    raise DownloadFailed(f"下载产物为空：{path}")
                return path, attempts
            except DownloadFailed:
                if attempts > self.download_retries:
                    raise
                delay = backoff_delay(attempts, base=2.0, cap=30.0)
                self._event(uid, "download_retry",
                            f"下载第 {attempts} 次失败 → {delay:.0f}s 后重下（不重生成）",
                            {"fingerprint": fp, "attempt": attempts}, "warning")
                self.sleep(delay)

    # ── 小工具 ────────────────────────────────────────────────
    def _cancelled(self) -> bool:
        return bool(getattr(self, "cancel_event", None)
                    and self.cancel_event.is_set())

    def _already_downloaded(self, row: dict, out_path: Path) -> bool:
        path = row.get("output_path")
        if path and Path(path).is_file() and Path(path).stat().st_size > 0:
            return True
        return out_path.is_file() and out_path.stat().st_size > 0

    def _outcome(self, out_path, task_id, wf, fp, prompt, meta, cost: float, *,
                 reused: bool, download_attempts: int) -> GenerationOutcome:
        return GenerationOutcome(
            video_path=Path(out_path), task_id=task_id, workflow=wf,
            cost=float(cost),
            fingerprint=fp, prompt_chars=len(prompt),
            compressed=bool(meta.get("compressed")), reused=reused,
            download_attempts=download_attempts, meta=dict(meta))

    def _event(self, uid: str, type_: str, message: str, data: dict,
               level: str = "info") -> None:
        with suppress(Exception):     # 事件失败不应中断出片
            self.store.add_event(uid, type_, message, stage=self.stage,
                                 data={**data, "level": level})
        if self.log is not None:
            self.log(f"  · {message}")


def _workflow_chain(workflow: str, fallbacks: Iterable[str]) -> list[str]:
    chain: list[str] = []
    for wf in [workflow, *list(fallbacks or [])]:
        if wf and wf not in chain:
            chain.append(wf)
    return chain or [workflow or "multi_image"]


def _default_payload(*, prompt: str, duration: int, resolution: str, ref_images,
                     ref_audios, root: Path) -> dict:
    from .providers import build_payload
    return build_payload(prompt=prompt, duration=duration, resolution=resolution,
                         ref_images=ref_images, ref_audios=ref_audios, root=root)
