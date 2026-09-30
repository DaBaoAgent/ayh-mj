"""Fake providers —— 让自动测试在 0 付费、0 联网下跑完整链路。

统计口径对齐 Phase 4/15 验收：create / query / download / llm 调用次数都必须可查，
用于断言"同一 attempt 不重复 create_task""下载失败只增加 download 次数"等。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CallLog:
    """按 provider 维度统计调用次数。"""

    create_task: int = 0
    query_task: int = 0
    download: int = 0
    llm: int = 0
    upload: int = 0
    submitted_tasks: list[dict] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {
            "create_task": self.create_task,
            "query_task": self.query_task,
            "download": self.download,
            "llm": self.llm,
            "upload": self.upload,
        }


@dataclass
class FakeEnv:
    """可安装到多个模块上的假供应商集合。"""

    log: CallLog = field(default_factory=CallLog)
    # 行为开关（测试按需改）
    fail_workflows: set[str] = field(default_factory=set)   # 这些工作流提交即失败
    download_fail_times: int = 0                            # 前 N 次下载失败
    llm_reply: str = "{}"
    llm_queue: list[str] = field(default_factory=list)      # 依次返回的回复
    task_counter: int = 0

    # ── AutoDL 行为 ────────────────────────────────────────
    def create_task(self, workflow_id: str, payload: dict, retries: int = 3) -> str:
        self.log.create_task += 1
        self.log.submitted_tasks.append({"workflow": workflow_id, "payload": payload})
        if workflow_id in self.fail_workflows:
            raise RuntimeError(f"fake provider rejected workflow {workflow_id}")
        self.task_counter += 1
        return f"fake_task_{self.task_counter}"

    def query_task(self, task_id: str, retries: int = 5) -> dict:
        self.log.query_task += 1
        return {"status": "SUCCESS", "results": [{"type": "video", "url": f"fake://{task_id}.mp4"}]}

    def poll_task(self, task_id: str, label: str = "", interval: int = 20,
                  max_wait: int = 1500, on_status=None) -> str:
        self.log.query_task += 1
        if on_status:
            on_status("SUCCESS", {})
        return f"fake://{task_id}.mp4"

    def download(self, url: str, out_path: str, retries: int = 4) -> str:
        self.log.download += 1
        if self.log.download <= self.download_fail_times:
            raise RuntimeError("fake download failure")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-mp4-bytes")
        return str(out)

    # ── LLM 行为 ───────────────────────────────────────────
    def chat(self, messages: list[dict], **kwargs) -> str:
        self.log.llm += 1
        if self.llm_queue:
            return self.llm_queue.pop(0)
        return self.llm_reply

    # ── Upload-Post 行为 ───────────────────────────────────
    def upload_video(self, video: str, title: str, platforms: list[str], **kwargs) -> dict:
        self.log.upload += 1
        return {"request_id": f"fake_req_{self.log.upload}", "platforms": platforms}

    def install(self, monkeypatch, *, autodl: bool = True, llm: bool = True,
                uploadpost: bool = True) -> None:
        if autodl:
            import s4_generate.autodl_client as ac
            monkeypatch.setattr(ac, "create_task", self.create_task, raising=False)
            monkeypatch.setattr(ac, "query_task", self.query_task, raising=False)
            monkeypatch.setattr(ac, "poll_task", self.poll_task, raising=False)
            monkeypatch.setattr(ac, "download", self.download, raising=False)
        if llm:
            import lib.llm as llm_mod
            monkeypatch.setattr(llm_mod, "chat", self.chat, raising=False)
        if uploadpost:
            try:
                import s6_publish.uploadpost as up
                monkeypatch.setattr(up, "upload_video", self.upload_video, raising=False)
            except Exception:
                pass

    def payload_json(self, i: int = 0) -> dict:
        return json.loads(json.dumps(self.log.submitted_tasks[i], default=str))


class FakeProvider:
    """实现 `ProviderAdapter` 协议的假供应商（Phase 4 幂等测试用）。

    与 `FakeEnv` 的区别：FakeEnv 打桩的是 `autodl_client` 的函数；FakeProvider 直接
    替身适配器对象本身，便于精确控制"崩在第几步"。
    """

    name = "fake"

    def __init__(self, env: FakeEnv | None = None) -> None:
        from lib.orchestrator.providers import ProviderTask
        self._Task = ProviderTask
        self.env = env or FakeEnv()
        self.submitted: list[dict] = []
        self.submit_attempts = 0           # 含被拒绝的提交尝试
        self.crash_on_query = False        # 模拟"提交成功后进程崩溃"
        self.query_calls = 0
        self.download_calls = 0
        self.fail_workflows: set[str] = set()
        self.download_fail_times = 0
        self.payload_bytes = b"fake-mp4-bytes"

    @property
    def submit_count(self) -> int:
        return len(self.submitted)

    def submit(self, *, payload: dict, workflow: str, meta: dict | None = None):
        from lib.orchestrator.errors import ProviderRejected
        self.submit_attempts += 1
        if workflow in self.fail_workflows:
            raise ProviderRejected(f"fake provider rejected workflow {workflow}")
        self.env.task_counter += 1
        task_id = f"fake_task_{self.env.task_counter}"
        self.submitted.append({"task_id": task_id, "workflow": workflow, "payload": payload})
        return self._Task(task_id=task_id, workflow=workflow, status="SUBMITTED")

    def query(self, task_id: str):
        if self.crash_on_query:
            raise RuntimeError("simulated crash after submit")   # 非 taxonomy 异常 = 崩溃
        self.query_calls += 1
        return self._Task(task_id=task_id, status="SUCCESS",
                          url=f"fake://{task_id}.mp4")

    def download(self, task, out_path: str) -> str:
        from lib.orchestrator.errors import DownloadFailed
        self.download_calls += 1
        if self.download_calls <= self.download_fail_times:
            raise DownloadFailed("fake download failure")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(self.payload_bytes)
        return str(out)
