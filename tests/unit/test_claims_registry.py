"""Phase 6 —— Claims Registry 结构/状态/可用性（必做任务 1、2）。"""
from __future__ import annotations

import datetime as dt

import pytest
import yaml

from lib import claims as claims_mod
from lib.claims import (
    CHANNELS,
    FORBIDDEN,
    KINDS,
    NEEDS_VERIFICATION,
    REQUIRED_FIELDS,
    STATUSES,
    VERIFIED,
    ClaimsRegistry,
    RegistryError,
    _claim_from_row,
    gate,
    load,
    registry,
    scan,
)

pytestmark = pytest.mark.unit

# 计划 §Phase 6 明确点名的 13 个字段
PLAN_FIELDS = ("claim_id", "sku", "display_text", "spoken_text", "value", "unit", "evidence",
               "certificate", "valid_from", "valid_to", "allowed_channels", "risk_level",
               "forbidden_rewrites")


def test_registry_file_exists_and_loads():
    reg = load(force=True)
    assert isinstance(reg, ClaimsRegistry)
    assert len(reg) >= 20
    assert reg.sku
    assert reg.evidence_doc.endswith(".md")


def test_every_claim_has_the_plan_required_fields():
    doc = yaml.safe_load(claims_mod.DEFAULT_PATH.read_text(encoding="utf-8"))
    for row in doc["claims"]:
        for field in PLAN_FIELDS:
            assert field in row, f"{row.get('claim_id')} 缺 {field}"
    assert set(PLAN_FIELDS) <= set(REQUIRED_FIELDS)


def test_claim_ids_are_unique_and_statuses_valid():
    reg = load(force=True)
    ids = [c.claim_id for c in reg.all()]
    assert len(ids) == len(set(ids))
    for c in reg.all():
        assert c.status in STATUSES
        assert c.kind in KINDS
        assert c.risk_level in {"low", "medium", "high"}
        for ch in c.allowed_channels:
            assert ch in CHANNELS


def test_verified_claims_always_carry_evidence():
    for c in load(force=True).verified():
        assert c.evidence, f"{c.claim_id} 是 verified 却没有 evidence"


def test_conflicting_parameters_are_marked_needs_verification():
    """任务 2：互相冲突的参数不允许 Codex 猜正确值。"""
    reg = load(force=True)
    nv = {c.claim_id for c in reg.needs_verification()}
    # 减震股数（18 股总 / 12 股护脊 冲突）与续航（16/25/39 随电池）
    assert "shock_18" in nv
    assert "range_39" in nv
    for c in reg.needs_verification():
        assert c.notes, f"{c.claim_id} 标了 needs_verification 却没写冲突原因"
        assert not c.allowed_channels, f"{c.claim_id} 待核验却仍声明可用渠道"


def test_forbidden_claims_are_never_auto_usable():
    reg = load(force=True)
    forbidden = reg.forbidden()
    assert forbidden, "绝对化广告词/价格政策必须至少有一条被禁"
    for c in forbidden:
        assert not c.usable("script")
        assert not c.usable("engage")
        assert c.notes


def test_validity_window_and_channel_limit_usable():
    today = dt.date(2026, 9, 30)
    ok = _claim_from_row({"claim_id": "x", "valid_from": "2026-01-01", "valid_to": "2026-12-31",
                          "allowed_channels": ["script"], "status": VERIFIED,
                          "evidence": "e"})
    assert ok.usable("script", today) and ok.in_window(today)
    assert not ok.usable("engage", today)          # 渠道不允许
    expired = _claim_from_row({"claim_id": "x", "valid_to": "2025-01-01", "status": VERIFIED,
                               "allowed_channels": ["script"], "evidence": "e"})
    assert not expired.usable("script", today)
    assert "有效期" in expired.block_reason("script", today)


def test_facts_block_only_contains_usable_claims():
    reg = load(force=True)
    block = reg.facts_block("script")
    assert block
    for c in reg.all():
        if not c.usable("script"):
            assert c.claim_id not in block, f"{c.claim_id} 不可用却出现在事实块里"
    # 待核验/禁止的口径绝不能出现在给 LLM 的事实块里
    assert "range_39" not in block and "shock_18" not in block and "guobu_15" not in block


def test_engage_channel_excludes_blocked_claims():
    reg = load(force=True)
    engage = reg.facts_block("engage")
    assert "lithium_safe" not in engage           # needs_verification
    assert "sales_rank_1" not in engage            # forbidden
    assert "light_13.8" in engage


def test_digest_changes_when_any_parameter_changes(tmp_path):
    reg = load(force=True)
    base = reg.digest()
    assert base == load().digest()                 # 稳定
    doc = yaml.safe_load(claims_mod.DEFAULT_PATH.read_text(encoding="utf-8"))
    for row in doc["claims"]:
        if row["claim_id"] == "light_13.8":
            row["value"] = 12.5
            row["display_text"] = "12.5kg 单手可提"
    alt = tmp_path / "claims_alt.yaml"
    alt.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert load(alt, force=True).digest() != base


def test_registry_rejects_broken_documents(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("claims:\n  - claim_id: a\n", encoding="utf-8")
    problems = claims_mod.validate_doc(yaml.safe_load(bad.read_text(encoding="utf-8")))
    assert problems, "缺字段的注册表必须被校验拦下"
    with pytest.raises(RegistryError):
        load(bad, force=True)


def test_registry_rejects_duplicate_and_unknown_status(tmp_path):
    doc = {"claims": [
        {"claim_id": "dup", "status": "unknown_state", "allowed_channels": []},
        {"claim_id": "dup", "status": VERIFIED},
    ]}
    problems = claims_mod.validate_doc(doc)
    assert any("重复" in p for p in problems)
    assert any("status" in p for p in problems)


def test_registry_rejects_verified_number_without_unit(tmp_path):
    doc = {"claims": [{"claim_id": "n", "status": VERIFIED, "kind": "number",
                       "value": 3, "unit": "", "evidence": "e", "allowed_channels": ["script"]}]}
    assert any("unit" in p for p in claims_mod.validate_doc(doc))


def test_registry_alias_and_status_counts():
    reg = registry(force=True)
    counts = reg.status_counts()
    assert set(counts) == set(STATUSES)
    assert counts[VERIFIED] + counts[NEEDS_VERIFICATION] + counts[FORBIDDEN] == len(reg)
    assert counts[NEEDS_VERIFICATION] >= 1 and counts[FORBIDDEN] >= 1
    assert isinstance(reg.by_kind("number"), list) and reg.by_kind("number")
    assert scan, gate                          # 导出可用
