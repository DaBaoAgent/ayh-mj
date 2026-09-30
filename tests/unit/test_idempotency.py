"""Phase 4 —— 幂等指纹 + 任务恢复 + 下载重试 + prompt 预算。

覆盖计划 §Phase 4 验收场景 1–4：
  1. H3 create_task 成功后进程崩溃 → 重启后只 query 原 task，不产生第二个提交；
  2. provider SUCCESS、下载失败两次 → 只发生下载重试（提交数不变）；
  3. prompt 超 10000 字 → 付费前压缩/阻断，AutoDL 提交数为 0；
  4. 连续 3 次 generation failed → job FAILED/BLOCKED，不无限烧钱。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator.errors import DOWNLOAD_FAILED, PromptTooLong
from lib.orchestrator.generation import (
    IdempotentGenerator,
    compress_prompt,
    cost_for,
    ensure_prompt_budget,
)
from lib.orchestrator.idempotency import fingerprint, refs_hash
from lib.orchestrator.models import STAGE_ORDER
from tests.fakes.providers import FakeProvider

pytestmark = pytest.mark.unit


def _gen(provider, root, **kw) -> IdempotentGenerator:
    kw.setdefault("sleep", lambda _s: None)
    kw.setdefault("poll_interval", 0.0)
    kw.setdefault("max_wait", 5.0)
    return IdempotentGenerator(store, provider, root=root, **kw)


def _spec(**over):
    spec = {
        "job_uid": over.pop("uid", "P4JOB"),
        "prompt": over.pop("prompt", "镜1：妈妈推着轮椅走进公园，特写轮子压过落叶。" * 3),
        "duration": over.pop("duration", 15),
        "resolution": over.pop("resolution", "768p竖"),
        "workflow": over.pop("workflow", "multi_image_15s"),
        "ref_images": over.pop("ref_images", []),
        "ref_audios": over.pop("ref_audios", []),
    }
    spec.update(over)
    return spec


# ── 1. 指纹（必做任务 1）──────────────────────────────────────
def test_fingerprint_is_deterministic_and_sensitive():
    base = dict(job_uid="J1", stage="generate", prompt="abc", refs=["a.png"],
                workflow="wf1")
    assert fingerprint(**base) == fingerprint(**base)
    assert fingerprint(**base) != fingerprint(**{**base, "prompt": "abd"})
    assert fingerprint(**base) != fingerprint(**{**base, "workflow": "wf2"})
    assert fingerprint(**base) != fingerprint(**{**base, "job_uid": "J2"})
    assert fingerprint(**base) != fingerprint(**{**base, "stage": "qa"})
    assert fingerprint(**base) != fingerprint(**{**base, "refs": ["b.png"]})


def test_refs_hash_tracks_file_size(tmp_path):
    p = tmp_path / "ref.png"
    p.write_bytes(b"x" * 10)
    h1 = refs_hash([str(p)])
    p.write_bytes(b"x" * 20)
    assert refs_hash([str(p)]) != h1, "素材变了指纹必须变"


# ── 2. prompt 预算（必做任务 6 / 验收场景 3）──────────────────
def test_compress_prompt_removes_duplicate_constraint_lines():
    text = "\n".join(["约束：角色一致", "画面：特写", "约束：角色一致", "", "", "结尾：定格"])
    out, changed = compress_prompt(text)
    assert changed
    assert out.count("约束：角色一致") == 1
    assert "\n\n\n" not in out
    assert "结尾：定格" in out                      # 不删镜头/不改内容


def test_ensure_prompt_budget_compresses_then_blocks():
    small = "短 prompt"
    assert ensure_prompt_budget(small)[0] == small
    # 靠重复行撑到 1 万字以上：压缩后回到安全线内
    bloated = "\n".join(["约束：角色一致与镜头衔接必须稳定"] * 900)
    text, meta = ensure_prompt_budget(bloated)
    assert meta["compressed"] and len(text) < 10000
    # 每行都不同 → 压不下去 → 阻断
    huge = "\n".join(f"第{i}条约束：唯一内容不可去重" for i in range(1000))
    with pytest.raises(PromptTooLong):
        ensure_prompt_budget(huge)


def test_prompt_too_long_blocks_before_any_submission(tmp_state):
    uid = "P4LONG"
    store.create_job(goal="超长", uid=uid)
    provider = FakeProvider()
    huge = "\n".join(f"第{i}条唯一约束：不可去重" for i in range(1200))
    assert len(huge) > 10000
    with pytest.raises(PromptTooLong):
        _gen(provider, tmp_state).generate(
            uid=uid, prompt=huge, duration=15, resolution="768p竖",
            workflow="multi_image_15s", out_path=tmp_state / "o.mp4")
    assert provider.submit_count == 0, "prompt 超限必须在付费前阻断（提交数=0）"
    assert store.list_provider_tasks(uid) == []


# ── 3. 崩溃恢复：只 query，不重提交（必做任务 2/3，验收场景 1）──
def test_crash_after_submit_never_resubmits(tmp_state):
    uid = "P4CRASH"
    store.create_job(goal="崩溃恢复", uid=uid)
    out = tmp_state / "out" / "gen_P4CRASH" / "onetake.mp4"
    provider = FakeProvider()
    provider.crash_on_query = True                     # 提交成功后进程崩溃

    with pytest.raises(RuntimeError):
        _gen(provider, tmp_state).generate(
            uid=uid, prompt="正常长度的 prompt", duration=15, resolution="768p竖",
            workflow="multi_image_15s", out_path=out)

    rows = store.list_provider_tasks(uid)
    assert provider.submit_count == 1, "提交只能发生一次"
    assert len(rows) == 1 and rows[0]["task_id"], "task_id 必须在轮询前就已落库"

    # 「重启」：崩溃原因消失后重跑 → 只 query 原 task
    provider.crash_on_query = False
    outcome = _gen(provider, tmp_state).generate(
        uid=uid, prompt="正常长度的 prompt", duration=15, resolution="768p竖",
        workflow="multi_image_15s", out_path=out)
    assert provider.submit_count == 1, "重启后不允许第二个提交"
    assert outcome.reused is True
    assert outcome.task_id == rows[0]["task_id"]
    assert out.is_file()
    assert store.list_provider_tasks(uid)[0]["status"] == "DONE"


def test_already_downloaded_task_is_skipped(tmp_state):
    uid = "P4DONE"
    store.create_job(goal="已完成", uid=uid)
    out = tmp_state / "done.mp4"
    out.write_bytes(b"x" * 100)
    fp = fingerprint(job_uid=uid, stage="generate", prompt="p", refs=[], workflow="wf",
                     root=tmp_state)
    store.upsert_provider_task(uid, fp, provider="fake", workflow="wf",
                               task_id="fake_task_9", status="DONE",
                               output_path=str(out))
    provider = FakeProvider()
    outcome = _gen(provider, tmp_state).generate(
        uid=uid, prompt="p", duration=15, resolution="768p竖", workflow="wf", out_path=out)
    assert outcome.reused is True
    assert provider.submit_count == 0 and provider.query_calls == 0
    assert provider.download_calls == 0


# ── 4. 下载失败只重下（必做任务 4，验收场景 2）─────────────────
def test_download_failure_only_retries_download(tmp_state):
    uid = "P4DL"
    store.create_job(goal="下载重试", uid=uid)
    out = tmp_state / "out" / "dl.mp4"
    provider = FakeProvider()
    provider.download_fail_times = 2                    # 前两次下载失败
    outcome = _gen(provider, tmp_state, download_retries=3).generate(
        uid=uid, prompt="正常 prompt", duration=15, resolution="768p竖",
        workflow="multi_image_15s", out_path=out)
    assert provider.submit_count == 1, "下载失败绝不能触发重新生成"
    assert provider.download_calls == 3, "应重下到成功为止"
    assert outcome.download_attempts == 3
    assert out.is_file()


def test_download_exhausted_does_not_resubmit(tmp_state):
    uid = "P4DL2"
    store.create_job(goal="下载全失败", uid=uid)
    provider = FakeProvider()
    provider.download_fail_times = 99
    from lib.orchestrator.errors import DownloadFailed
    with pytest.raises(DownloadFailed):
        _gen(provider, tmp_state, download_retries=2).generate(
            uid=uid, prompt="正常 prompt", duration=15, resolution="768p竖",
            workflow="multi_image_15s", out_path=tmp_state / "never.mp4")
    assert provider.submit_count == 1
    assert provider.download_calls == 3                 # 1 次 + 2 次重试
    row = store.list_provider_tasks(uid)[0]
    assert row["status"] == "FAILED" and row["error_code"] == DOWNLOAD_FAILED


# ── 5. workflow 切换 ──────────────────────────────────────────
def test_workflow_fallback_switches_chain(tmp_state):
    uid = "P4WF"
    store.create_job(goal="换链", uid=uid)
    provider = FakeProvider()
    provider.fail_workflows = {"wf_bad"}
    outcome = _gen(provider, tmp_state).generate(
        uid=uid, prompt="正常 prompt", duration=15, resolution="768p竖",
        workflow="wf_bad", fallback_workflows=["wf_good"],
        out_path=tmp_state / "wf.mp4")
    assert provider.submit_attempts == 2, "首个 workflow 被拒后要尝试下一条链"
    assert outcome.workflow == "wf_good"
    assert [s["workflow"] for s in provider.submitted] == ["wf_good"]


def test_events_record_fingerprint_and_reason(tmp_state):
    uid = "P4EV"
    store.create_job(goal="事件", uid=uid)
    provider = FakeProvider()
    provider.download_fail_times = 1
    _gen(provider, tmp_state, download_retries=2).generate(
        uid=uid, prompt="正常 prompt", duration=15, resolution="768p竖",
        workflow="multi_image_15s", out_path=tmp_state / "ev.mp4")
    kinds = [e["type"] for e in store.list_events(uid)]
    assert "provider_submitted" in kinds and "download_retry" in kinds
    submitted = next(e for e in store.list_events(uid) if e["type"] == "provider_submitted")
    assert submitted["data"]["fingerprint"]      # 指纹可追溯
    assert submitted["data"]["prompt_hash"]


# ── 6. 编排层端到端（假供应商，0 付费）────────────────────────
def _stages(**overrides):
    def make(name):
        def fn(ctx):
            return StageResult.ok(name, metrics={})
        return fn
    stages = {name: make(name) for name in STAGE_ORDER}
    stages.update(overrides)
    return stages


def _queue_spec(tmp_state, spec: dict) -> Path:
    q = tmp_state / "queue_15s"
    q.mkdir(parents=True, exist_ok=True)
    p = q / f"{spec['job_uid']}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return p


def test_orchestrator_generate_stage_uses_idempotent_driver(tmp_state):
    provider = FakeProvider()
    provider.payload_bytes = b"v" * 150_000           # 过 qa 体量门限
    uid = "P4E2E"
    _queue_spec(tmp_state, _spec(uid=uid))
    orch = PipelineOrchestrator(store=store, queue_dir=tmp_state / "queue_15s",
                                root=tmp_state, provider=provider,
                                sleep=lambda _s: None, poll_interval=0.0)
    result = orch.start(RunConfig(goal="端到端", daily_target=1, source="test",
                                  stages=["plan", "generate", "qa"]), background=False)
    assert result["jobs"] == [uid]
    job = store.get_job(uid)
    assert job["status"] == JobState.QA
    assert job["cost_spent"] == pytest.approx(cost_for(15, "768p竖"))
    assert provider.submit_count == 1
    tasks = store.list_provider_tasks(uid)
    assert len(tasks) == 1 and tasks[0]["status"] == "DONE"
    gen_events = [e for e in store.list_events(uid) if e["type"] == "provider_submitted"]
    assert len(gen_events) == 1


def test_orchestrator_crash_then_retry_keeps_single_submission(tmp_state):
    provider = FakeProvider()
    provider.crash_on_query = True
    uid = "P4CRASH2"
    _queue_spec(tmp_state, _spec(uid=uid))
    orch = PipelineOrchestrator(store=store, queue_dir=tmp_state / "queue_15s",
                                root=tmp_state, provider=provider,
                                sleep=lambda _s: None, poll_interval=0.0)
    orch.start(RunConfig(goal="崩溃", daily_target=1, source="test",
                         stages=["plan", "generate"]), background=False)
    assert store.get_job(uid)["status"] == JobState.FAILED
    assert provider.submit_count == 1

    provider.crash_on_query = False
    out = orch.retry(uid, background=False)
    assert out["ok"]
    assert provider.submit_count == 1, "恢复后仍只允许一次提交"
    assert store.get_job(uid)["status"] == JobState.GENERATING
