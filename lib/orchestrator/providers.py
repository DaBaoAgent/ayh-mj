"""供应商适配层（Phase 4 引入，Phase 7 统一为 `ProviderTask`）。

存在的理由：业务层（编排/生成/质检）只应看到 `ProviderTask`，不碰 AutoDL 私有字段。
  · `submit()` 拿到 task_id 立刻返回，调用方**必须**马上落 DB（见 generation.py）；
  · `query()` 可安全重试（GET）；
  · `download()` 单独一个方法 —— 因为"下载失败"绝不允许触发重新生成（Phase 4 必做任务 4）；
  · 所有异常都翻译成 errors.py 的 taxonomy 异常，业务层只认 error_code。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .errors import (
    ASSET_MISSING,
    AUTH_EXPIRED,
    CONFIG_MISSING,
    DOWNLOAD_FAILED,
    GENERATION_TIMEOUT,
    NETWORK_TRANSIENT,
    PROMPT_TOO_LONG,
    PROVIDER_REJECTED,
    RATE_LIMIT,
    AssetMissing,
    AuthExpired,
    ConfigMissing,
    DownloadFailed,
    GenerationTimeout,
    NetworkTransient,
    PromptTooLong,
    ProviderError,
    ProviderRejected,
    RateLimited,
    classify_exception,
)

# 供应商返回的状态 → canonical
SUCCESS_STATES = frozenset({"SUCCESS", "SUCCEEDED", "DONE", "COMPLETE"})
FAILED_STATES = frozenset({"FAILED", "ERROR", "CANCELLED", "CANCELED", "TIMEOUT"})


@dataclass
class ProviderTask:
    """业务层唯一可见的供应商任务对象。"""

    task_id: str
    workflow: str = ""
    status: str = "SUBMITTED"
    url: str = ""
    cost: float = 0.0
    raw: dict = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status.upper() in SUCCESS_STATES

    @property
    def failed(self) -> bool:
        return self.status.upper() in FAILED_STATES

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "workflow": self.workflow, "status": self.status,
                "url": self.url, "cost": self.cost}


class ProviderAdapter(Protocol):
    """供应商适配器协议（AutoDL / fake 都实现它）。"""

    name: str

    def submit(self, *, payload: dict, workflow: str, meta: dict | None = None) -> ProviderTask: ...
    def query(self, task_id: str) -> ProviderTask: ...
    def download(self, task: ProviderTask, out_path: str) -> str: ...


_CODE_EXC: dict[str, type[ProviderError]] = {
    CONFIG_MISSING: ConfigMissing,
    AUTH_EXPIRED: AuthExpired,
    NETWORK_TRANSIENT: NetworkTransient,
    RATE_LIMIT: RateLimited,
    PROMPT_TOO_LONG: PromptTooLong,
    ASSET_MISSING: AssetMissing,
    PROVIDER_REJECTED: ProviderRejected,
    GENERATION_TIMEOUT: GenerationTimeout,
    DOWNLOAD_FAILED: DownloadFailed,
}


def translate_error(exc: BaseException, *, default: type[ProviderError] = ProviderRejected
                    ) -> ProviderError:
    """任意供应商异常 → taxonomy 异常（业务层只认 error_code）。"""
    if isinstance(exc, ProviderError):
        return exc
    code = classify_exception(exc)
    cls = _CODE_EXC.get(code, default)
    return cls(str(exc)[:300], data={"error_code": code, "raw_type": type(exc).__name__})


def build_payload(*, prompt: str, duration: int, resolution: str, ref_images=(),
                  ref_audios=(), root: Path | None = None, to_data_url=None) -> dict:
    """构造 AutoDL payload（参考素材转 data URL；与 gen_one_take 同口径）。"""
    if to_data_url is None:
        from s4_generate.autodl_client import to_data_url as _tdu
        to_data_url = _tdu
    root = Path(root) if root is not None else Path.cwd()

    def _resolve(p) -> str:
        q = Path(p)
        return str(q if q.is_absolute() else root / q)

    payload: dict = {"prompt": prompt, "duration": int(duration), "resolution": resolution}
    for i, img in enumerate(list(ref_images)[:9]):
        payload[f"ref_image_{i}"] = to_data_url(_resolve(img))
    for i, aud in enumerate(list(ref_audios)[:3]):
        payload[f"ref_audio_{i}"] = to_data_url(_resolve(aud), resize=False)
    return payload


class AutoDLProvider:
    """AutoDL.Art MiniMax H3 适配器（薄封装 s4_generate.autodl_client）。"""

    name = "autodl"

    def __init__(self, client=None, *, workflow_map: dict | None = None) -> None:
        self._client = client
        self._workflow_map = workflow_map

    def _c(self):
        if self._client is None:
            from s4_generate import autodl_client as ac
            self._client = ac
        return self._client

    def resolve_workflow(self, workflow: str) -> str:
        mapping = self._workflow_map
        if mapping is None:
            mapping = getattr(self._c(), "WORKFLOWS", {}) or {}
        return mapping.get(workflow, workflow)

    def submit(self, *, payload: dict, workflow: str, meta: dict | None = None) -> ProviderTask:
        try:
            task_id = self._c().create_task(self.resolve_workflow(workflow), payload)
        except Exception as exc:  # noqa: BLE001 —— 统一翻译成 taxonomy
            raise translate_error(exc) from exc
        if not task_id:
            raise ProviderRejected("提交成功但未返回 task_id（供应商响应异常）")
        return ProviderTask(task_id=str(task_id), workflow=workflow, status="SUBMITTED")

    def query(self, task_id: str) -> ProviderTask:
        try:
            data = self._c().query_task(task_id)
        except Exception as exc:  # noqa: BLE001
            raise translate_error(exc, default=_CODE_EXC[NETWORK_TRANSIENT]) from exc
        data = data or {}
        status = str(data.get("status") or "UNKNOWN").upper()
        url = ""
        results = data.get("results") or []
        if results:
            first = results[0]
            url = (first.get("url") if isinstance(first, dict) else str(first)) or ""
        return ProviderTask(task_id=task_id, status=status, url=url.strip(), raw=data)

    def download(self, task: ProviderTask, out_path: str) -> str:
        target = task.url or task.task_id
        try:
            return str(self._c().download(target, str(out_path)))
        except Exception as exc:  # noqa: BLE001
            raise DownloadFailed(f"下载失败：{str(exc)[:200]}",
                                 data={"task_id": task.task_id}) from exc
