"""Phase 4 —— error taxonomy / RepairEngine 白名单 / 阶段策略 / 预算保护。

对应计划的必做任务 5–10 与验收场景 4、5。
"""
from __future__ import annotations

import pytest

from lib.jobstore import JobState
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator.errors import (
    ABORT,
    ALL_CODES,
    BUSINESS_CODES,
    COMPLIANCE_BLOCK,
    GENERATION_FAILED,
    NETWORK_TRANSIENT,
    PROMPT_TOO_LONG,
    PUBLISH_QUOTA,
    RATE_LIMIT,
    REGENERATE_SHOT,
    REPAIR_ACTIONS,
    REPAIR_MAP,
    REQUIRE_HUMAN,
    RETRY_SAME,
    RETRYABLE_CODES,
    SWITCH_WORKFLOW,
    UNKNOWN,
    WAIT_AND_RESUME,
    backoff_delay,
    classify_exception,
    repair_action_for,
)
from lib.orchestrator.models import STAGE_ORDER
from lib.orchestrator.policies import policy_for
from lib.orchestrator.recovery import RepairEngine

pytestmark = pytest.mark.unit

# 计划 §Phase 4 明确要求的最小 error taxonomy
REQUIRED_CODES = (
    "CONFIG_MISSING", "AUTH_EXPIRED", "NETWORK_TRANSIENT", "RATE_LIMIT",
    "PROMPT_TOO_LONG", "ASSET_MISSING", "PROVIDER_REJECTED", "GENERATION_FAILED",
    "GENERATION_TIMEOUT", "DOWNLOAD_FAILED", "ASR_MISMATCH", "SUBTITLE_ALIGN_FAIL",
    "VISUAL_QA_FAIL", "PRODUCT_DEFORMED", "WRONG_SPEAKER", "HUMAN_ANATOMY_FAIL",
    "COMPLIANCE_BLOCK", "PUBLISH_QUOTA", "PUBLISH_AUTH", "UNKNOWN",
)


# ── 1. taxonomy 完整性（必做任务 1..）──────────────────────────
def test_error_taxonomy_is_complete():
    for code in REQUIRED_CODES:
        assert code in ALL_CODES, f"taxonomy 缺少 {code}"
    assert len(BUSINESS_CODES) == 20


def test_every_repair_action_is_whitelisted():
    assert set(REPAIR_MAP.values()) <= set(REPAIR_ACTIONS)
    assert set(REPAIR_MAP) <= set(ALL_CODES)
    # 白名单就是计划里点名的这 8 个动作，不多不少
    assert set(REPAIR_ACTIONS) == {
        "RETRY_SAME", "SWITCH_WORKFLOW", "COMPRESS_PROMPT", "REGENERATE_SHOT",
        "REBUILD_SUBTITLE", "WAIT_AND_RESUME", "REQUIRE_HUMAN", "ABORT"}


def test_in_stage_actions_are_retryable_only():
    for code, action in REPAIR_MAP.items():
        if action in ("RETRY_SAME",):
            assert code in RETRYABLE_CODES, f"{code} 标成 RETRY_SAME 却不可重试"
        if action in ("WAIT_AND_RESUME", "REQUIRE_HUMAN", "ABORT"):
            assert code not in RETRYABLE_CODES or action != "ABORT"


def test_unknown_code_maps_to_abort():
    assert repair_action_for("NOT_A_REAL_CODE") == ABORT
    assert repair_action_for(None) == ABORT
    assert repair_action_for(UNKNOWN) == ABORT


def test_backoff_is_exponential_and_capped():
    delays = [backoff_delay(i) for i in range(1, 8)]
    assert delays[0] == 2.0 and delays[1] == 4.0 and delays[2] == 8.0
    assert delays == sorted(delays)
    assert max(delays) <= 60.0


def test_classify_exception_maps_provider_messages():
    assert classify_exception("参数: prompt 的长度: 11506 大于最大长度 10000") == PROMPT_TOO_LONG
    assert classify_exception("提交失败: invalid workflow") == "PROVIDER_REJECTED"
    assert classify_exception("Connection reset by peer (10054)") == NETWORK_TRANSIENT
    assert classify_exception("429 too many requests") == RATE_LIMIT
    assert classify_exception("下载失败（4 次）: timeout") == "DOWNLOAD_FAILED"
    assert classify_exception("something nobody has seen") == UNKNOWN


# ── 2. RepairEngine 决策（必做任务 8/9/10）─────────────────────
def test_success_continues():
    engine = RepairEngine()
    decision = engine.decide(StageResult.ok("generate"), stage="generate")
    assert decision.action == "continue" and decision.can_continue


def test_transient_error_retries_with_backoff():
    engine = RepairEngine()
    d = engine.decide(StageResult.fail("generate", NETWORK_TRANSIENT, "抖动"),
                      attempts=1, stage="generate")
    assert d.action == RETRY_SAME and d.can_continue
    assert d.delay > 0, "瞬时网络错误必须退避"


def test_business_error_is_not_retried_forever():
    engine = RepairEngine()
    d = engine.decide(StageResult.fail("generate", COMPLIANCE_BLOCK, "违规"),
                      attempts=1, stage="generate")
    assert d.action == REQUIRE_HUMAN and not d.can_continue
    assert d.terminal_state == JobState.BLOCKED


def test_publish_quota_waits_instead_of_counting_as_generation_failure():
    engine = RepairEngine()
    d = engine.decide(StageResult.fail("publish", PUBLISH_QUOTA, "今日已达上限"),
                      attempts=1, stage="publish")
    assert d.action == WAIT_AND_RESUME
    assert d.terminal_state == JobState.PAUSED
    assert not d.can_continue


def test_attempts_exhausted_aborts():
    engine = RepairEngine()
    d = engine.decide(StageResult.fail("generate", GENERATION_FAILED, "第 3 次"),
                      attempts=3, stage="generate")
    assert d.action == ABORT and "上限" in d.reason


def test_workflow_rejection_switches_workflow():
    engine = RepairEngine()
    d = engine.decide(StageResult.fail("generate", "PROVIDER_REJECTED", "工作流不支持"),
                      attempts=1, stage="generate")
    assert d.action == SWITCH_WORKFLOW and d.can_continue


def test_stage_policy_whitelist_is_stage_scoped():
    """Phase 8：qa 阶段已把 VISUAL_QA_FAIL 纳入白名单（→ 重出成片），
    而 generate 阶段的白名单不含该码 —— 同一 error_code 在不同阶段行为不同。"""
    engine = RepairEngine()
    d = engine.decide(StageResult.fail("qa", "VISUAL_QA_FAIL", "画面差"),
                      attempts=1, stage="qa")
    assert d.action == REGENERATE_SHOT and d.can_continue
    # generate 阶段白名单不含 VISUAL_QA_FAIL → 拒绝在本阶段重跑
    d2 = engine.decide(StageResult.fail("generate", "VISUAL_QA_FAIL", "画面差"),
                       attempts=1, stage="generate")
    assert d2.action == ABORT



# ── 3. 阶段策略（必做任务 6）──────────────────────────────────
def test_every_stage_declares_policy():
    for stage in STAGE_ORDER:
        policy = policy_for(stage)
        assert policy.max_attempts >= 1
        assert policy.max_cost is not None
        assert isinstance(policy.repairable, tuple)
    assert policy_for("generate").max_cost > 0, "付费阶段必须有单阶段成本上限"
    assert policy_for("generate").max_attempts == 3
    assert policy_for("unknown-stage").max_attempts == 1


def test_policy_allows_retry_respects_whitelist_and_limit():
    policy = policy_for("generate")
    assert policy.allows_retry(GENERATION_FAILED, 1)
    assert not policy.allows_retry(GENERATION_FAILED, 3)
    assert not policy.allows_retry("COMPLIANCE_BLOCK", 1)


# ── 4. 预算保护（必做任务 7）──────────────────────────────────
def _stages(**overrides):
    def make(name):
        return lambda ctx: StageResult.ok(name, metrics={})
    stages = {name: make(name) for name in STAGE_ORDER}
    stages.update(overrides)
    return stages


def test_job_budget_blocks_paid_stage_before_spending(tmp_state):
    from lib.jobstore import store
    orch = PipelineOrchestrator(store=store, stages=_stages(), queue_dir=tmp_state / "q",
                                root=tmp_state)
    uid = store.create_job(goal="预算不足", uid="P4BUDGET", budget_cap=1.0)
    store.add_cost(uid, 0.5)          # 已花 0.5，剩 0.5 < generate 阶段上限 1.2
    orch._execute(uid, RunConfig(goal="预算不足", stages=["generate"]))
    job = store.get_job(uid)
    assert job["status"] == JobState.BLOCKED
    assert job["error_code"] == "BLOCKED_BUDGET"


def test_job_budget_blocks_when_already_over(tmp_state):
    from lib.jobstore import store
    orch = PipelineOrchestrator(store=store, stages=_stages(), queue_dir=tmp_state / "q",
                                root=tmp_state)
    uid = store.create_job(goal="超预算", uid="P4BUDGET2", budget_cap=1.0)
    store.add_cost(uid, 1.5)
    orch._execute(uid, RunConfig(goal="超预算", stages=["generate"]))
    assert store.get_job(uid)["status"] == JobState.BLOCKED


# ── 5. 编排层：配额等待 ≠ 生成失败（验收场景 5）───────────────
def test_quota_failure_pauses_job_not_fails(tmp_state):
    from lib.jobstore import store
    stages = _stages(qa=lambda ctx: StageResult.fail("qa", PUBLISH_QUOTA, "今日已达上限"))
    orch = PipelineOrchestrator(store=store, stages=stages, queue_dir=tmp_state / "q",
                                root=tmp_state)
    uid = orch.start(RunConfig(goal="配额", daily_target=1, source="test"),
                     background=False)["jobs"][0]
    job = store.get_job(uid)
    assert job["status"] == JobState.PAUSED, "配额不是生成失败，不能进 FAILED"
    assert job["error_code"] == PUBLISH_QUOTA
    # 且 decision 已写入 events（可追溯为什么这么处理）
    failed = [e for e in store.list_events(uid) if e["type"] == "stage_failed"]
    assert failed[0]["data"]["decision"] == WAIT_AND_RESUME
    assert failed[0]["data"]["reason"]                    # 为什么这样修
    assert failed[-1]["data"]["repair_action"] == WAIT_AND_RESUME
