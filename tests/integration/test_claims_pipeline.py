"""Phase 6 端到端 —— 未登记/待核验/禁用口径必须在付费生成之前收口。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import claims as claims_mod
from lib.jobstore import JobState, store
from lib.orchestrator import PipelineOrchestrator, RunConfig, StageResult
from lib.orchestrator import stages as stages_mod
from lib.orchestrator.errors import (
    CLAIM_FORBIDDEN,
    CLAIM_NEEDS_VERIFICATION,
    CLAIM_UNMAPPED,
    MISSING_INPUT,
)
from lib.orchestrator.models import STAGE_ORDER
from tests.fakes.providers import FakeProvider

pytestmark = pytest.mark.integration

CLAIM_CODES = {CLAIM_UNMAPPED, CLAIM_NEEDS_VERIFICATION, CLAIM_FORBIDDEN}


def _fake(name):
    def fn(ctx):
        return StageResult.ok(name, metrics={})
    return fn


def _stages(**overrides):
    stages = {name: _fake(name) for name in STAGE_ORDER}
    stages.update(overrides)
    return stages


def _orch(tmp_state, provider, stages) -> PipelineOrchestrator:
    return PipelineOrchestrator(store=store, stages=stages, provider=provider,
                                queue_dir=tmp_state / "queue_15s", root=tmp_state)


def _cfg(**kw) -> RunConfig:
    kw.setdefault("source", "test")
    kw.setdefault("daily_target", 1)
    return RunConfig(**kw)


def _write_spec(tmp_state, uid, payoff, claims=()) -> Path:
    queue = tmp_state / "queue_15s"
    queue.mkdir(parents=True, exist_ok=True)
    spec = {
        "job_uid": uid,
        "title": f"测试片 {uid}",
        "plan_only": False,          # 假装 prompt 已编译，好走到 Phase 6 合规门
        "prompt_ready": True,
        "claim_ids": list(claims),
        "creative": {"dna": {"payoff": payoff}, "claim_ids": list(claims)},
        "story_spec": {"prompt": "", "shots": []},
    }
    path = queue / f"{uid}.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _run(tmp_state, spec_path, uid):
    provider = FakeProvider()
    orch = _orch(tmp_state, provider, _stages(plan=stages_mod.stage_plan,
                                             preflight=stages_mod.stage_preflight))
    result = orch.start(_cfg(), specs=[spec_path], background=False)
    return provider, result, store.get_job(uid)


def _spec_doc(tmp_state, uid, artifact_path):
    """出片成功后 spec 会被归档进 queue_15s/_done/，artifact 路径可能已失效。"""
    path = Path(artifact_path) if artifact_path else None
    if not (path and path.is_file()):
        found = list((tmp_state / "queue_15s").rglob(f"{uid}.json"))
        path = found[0] if found else None
    assert path and path.is_file(), f"找不到 spec 文件：{artifact_path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("payoff,code", [
    ("充电只要20分钟", CLAIM_UNMAPPED),
    ("承重150公斤，全家人都能用", CLAIM_UNMAPPED),
    ("国家医疗器械认证", CLAIM_NEEDS_VERIFICATION),
    ("电池是医疗级的", CLAIM_NEEDS_VERIFICATION),
    ("高端轮椅销量第一", CLAIM_FORBIDDEN),
    ("约20kg，单手可拎", CLAIM_FORBIDDEN),
])
def test_compliance_gate_blocks_before_paid_generation(tmp_state, payoff, code):
    uid = "CLAIMBLK1"
    spec = _write_spec(tmp_state, uid, payoff)
    provider, result, job = _run(tmp_state, spec, uid)

    assert uid in result["jobs"], result
    assert job["status"] == JobState.BLOCKED, job
    assert job["error_code"] == code, (job["error_code"], job["error"])
    assert provider.submit_count == 0, "合规门不通过绝不能触发付费提交"
    assert [a["stage"] for a in store.list_attempts(uid)] == ["plan", "preflight"]
    assert not (tmp_state / "out" / f"gen_{uid}").exists()


def test_registered_and_usable_claim_passes_the_gate(tmp_state):
    uid = "CLAIMOK1"
    spec = _write_spec(tmp_state, uid, "3.0 防翻系统，30度陡坡不后翻", claims=["anti_flip"])
    provider, result, job = _run(tmp_state, spec, uid)

    assert provider.submit_count == 0
    # 合规门已放行 —— 卡在后面的台词文件（Phase 7 之前不产出）
    assert job["error_code"] == MISSING_INPUT, job
    assert job["error_code"] not in CLAIM_CODES


def test_planner_registers_a_claims_artifact_matching_the_spec(tmp_state):
    """任务 7：发布 artifact 必须带 claim_id 列表，且与 spec 完全一致。"""
    provider = FakeProvider()
    orch = _orch(tmp_state, provider, _stages(plan=stages_mod.stage_plan))
    result = orch.start(_cfg(), background=False)
    assert result["ok"] and result["count"] == 1, result

    uid = result["jobs"][0]
    arts = {a["type"]: a["path"] for a in store.list_artifacts(uid)}
    assert {"spec", "claims"} <= set(arts)

    claims_doc = json.loads(Path(arts["claims"]).read_text(encoding="utf-8"))
    spec_doc = _spec_doc(tmp_state, uid, arts.get("spec"))
    reg = claims_mod.load()

    assert claims_doc["claim_ids"] == spec_doc["claim_ids"]
    assert claims_doc["claim_ids"], "自主规划至少要登记一条产品 claim"
    assert all(claims_doc["usable"].values())
    assert claims_doc["gate"]["ok"] is True
    assert claims_doc["digest"] == reg.digest()[:16]
    for cid in claims_doc["claim_ids"]:
        assert reg.get(cid) is not None, cid


def test_blocked_claims_never_reach_the_spec_artifact(tmp_state):
    """规划阶段就把不可用卖点挡在 payoff 之外（Phase 6 + Phase 5 的接缝）。"""
    provider = FakeProvider()
    orch = _orch(tmp_state, provider, _stages(plan=stages_mod.stage_plan))
    result = orch.start(_cfg(), background=False)
    uid = result["jobs"][0]
    arts = {a["type"]: a["path"] for a in store.list_artifacts(uid)}
    spec_doc = _spec_doc(tmp_state, uid, arts.get("spec"))
    assert spec_doc["plan_only"] is True
    assert not spec_doc["prompt"], "prompt 未编译前必须是空串（Phase 7 才填）"
