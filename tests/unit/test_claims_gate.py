"""Phase 6 —— 合规门（必做任务 4、5；验收标准「未登记参数必须阻断」）。"""
from __future__ import annotations

import pytest

from lib import claims as claims_mod
from lib.claims import FORBIDDEN, NEEDS_VERIFICATION, VERIFIED, claim_ids_in, gate, scan

pytestmark = pytest.mark.unit

# (文本, 渠道, 期望 ok, 期望 error 类别)
CASES = [
    ("3.0 防翻系统，30度陡坡不后翻", "script", True, ""),
    ("十三点八公斤，一只手就拎起来", "script", True, ""),
    ("CNAS认证，能上飞机，免费托运", "script", True, ""),
    ("松手就停，坡上也不溜", "engage", True, ""),
    ("四公分到七公分加厚坐垫", "script", True, ""),
    ("2年质保，车架终身售后", "packaging", True, ""),
    ("承重一百公斤，全家人都能用", "script", True, ""),
    # 未登记参数 —— 必须阻断
    ("承重150公斤，全家都能用", "script", False, "unmapped"),
    ("续航 800 公里", "script", False, "unmapped"),
    ("充电只要 20 分钟", "script", False, "unmapped"),
    # 禁用改写 —— 冲突参数
    ("约20kg，单手可拎", "engage", False, "forbidden"),
    # shock_18 口径冲突（18 股总数 vs 12 股护脊），两种写法都在禁用改写里 → 判定违禁改写
    ("18股护脊减震，汽车级的", "script", False, "forbidden"),
    ("充一次跑39公里", "script", False, "forbidden"),
    ("高端轮椅销量第一", "packaging", False, "forbidden"),
    ("国补15%", "packaging", False, "forbidden"),
    # 医疗疗效 —— 绝对禁止
    ("能治疗腿脚不便", "engage", False, "unmapped"),
    ("康复效果显著", "script", False, "unmapped"),
    # 未证实认证
    ("国家医疗器械认证", "script", False, "nv"),
    ("27项研发专利，独家", "script", False, "nv"),
    # 绝对化
    # 「绝对安全」是 anti_flip 的禁用改写（把「30度陡坡不后翻」升级成承诺）→ 判定违禁改写
    ("这是绝对安全的轮椅", "script", False, "forbidden"),
]


def _category(result) -> str:
    kinds = {f.kind for f in result.unmapped} | {f.kind for f in result.blocked}
    if "forbidden_rewrite" in kinds:
        return "forbidden"
    if any("forbidden" in (f.blocked_reason or "") for f in result.blocked):
        return "forbidden"
    if result.unmapped:
        return "unmapped"
    return "nv"


@pytest.mark.parametrize("text,channel,expect_ok,expect_cat", CASES)
def test_gate_matrix(text, channel, expect_ok, expect_cat):
    result = gate(text, channel)
    assert result.ok == expect_ok, f"{text} -> {result.message()}"
    if not expect_ok:
        assert _category(result) == expect_cat, f"{text} -> {result.message()}"


def test_unregistered_number_is_blocked_not_waved_through():
    """验收标准②：故意输出未登记参数，必须阻断而不是"看起来合理就通过"。"""
    result = gate("这车能跑500公里，承重200公斤", "script")
    assert not result.ok
    texts = {f.text for f in result.unmapped}
    assert "500公里" in texts and "200公斤" in texts
    assert result.claim_ids == []


def test_plausible_but_unregistered_certificate_is_blocked():
    result = gate("通过欧盟CE认证，获得德国红点奖", "script")
    assert not result.ok


def test_forbidden_rewrite_is_reported_as_conflict_with_the_claim():
    result = gate("约20kg", "engage")
    finding = next(f for f in result.findings if f.kind == "forbidden_rewrite")
    assert finding.claim_id == "light_13.8"
    assert "13.8" in finding.blocked_reason or "禁用改写" in finding.blocked_reason


def test_mapped_claims_are_reported_for_traceability():
    result = gate("3.0 防翻系统，30度陡坡不后翻；刹车灯自动亮", "script")
    assert result.ok
    assert "anti_flip" in result.claim_ids and "brake_light" in result.claim_ids
    assert claim_ids_in("刹车灯自动亮") == ["brake_light"]


def test_channel_scoping_blocks_claim_not_allowed_on_that_channel():
    # aftersales_service 只允许 packaging / engage
    assert gate("15 天免费试用", "packaging").ok
    blocked = gate("15 天免费试用", "script")
    assert not blocked.ok
    assert "渠道" in blocked.message()


def test_clean_text_without_claims_passes():
    result = gate("奶奶用这个好方便啊，谢谢分享", "engage")
    assert result.ok and result.claim_ids == []


def test_needs_verification_claim_blocks_even_when_mapped():
    result = gate("十八股减震", "script")
    assert not result.ok
    f = result.blocked[0]
    assert f.claim_id == "shock_18"
    assert "needs_verification" in f.blocked_reason


def test_forbidden_claim_status_blocks():
    sm = {c.claim_id: c.status for c in claims_mod.load().all()}
    assert sm["sales_rank_1"] == FORBIDDEN and sm["range_39"] == NEEDS_VERIFICATION
    assert sm["light_13.8"] == VERIFIED


def test_scan_reports_spans_and_kinds():
    findings = scan("承重150公斤，能治疗腿脚不便")
    kinds = {f.kind for f in findings}
    assert "numeric" in kinds and "medical" in kinds
    for f in findings:
        assert f.span[0] < f.span[1]


def test_gate_result_serializes_for_artifacts():
    payload = gate("承重150公斤", "script").to_dict()
    assert payload["ok"] is False
    assert payload["unmapped"] and payload["message"]
    assert set(payload) >= {"ok", "channel", "claim_ids", "unmapped", "blocked", "findings"}
