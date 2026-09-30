"""Phase 13 单测 —— 契约表自身的正确性（不联网、不付费）。

这里冻结的是"契约的语义"，不是第三方实现：
  · 每个契约都有 endpoint / consumer / 至少一条规则或自定义校验，
  · fixture 目录里每个契约名都至少有一份正例（新增契约忘了配样本会红），
  · 路径探针 `a[].b` 会逐项校验，`when` 条件未满足时不误报，
  · assert_contract 报错必须点名到字段（而不是丢一句 KeyError 给上层），
  · PostFlow 凭据失效信号在 lib.contracts 与生产模块之间**不漂移**。
"""
from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from lib import contracts
from lib.contracts import (
    CONTRACTS,
    ContractError,
    assert_contract,
    is_valid,
    names,
    postflow_command_flags,
    postflow_is_auth_error,
    validate,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"


def _fixture_contracts(sub: str) -> set[str]:
    return {p.name.split(".")[0] for p in (FIXTURES / sub).glob("*.json")}


# ── 契约表本身 ─────────────────────────────────────────────────────────

def test_names_are_sorted_unique_and_match_the_table():
    assert names() == tuple(sorted(CONTRACTS))
    assert len(set(names())) == len(names())
    assert names(), "契约表不能是空的"


def test_every_contract_declares_endpoint_consumer_and_rules():
    for name in names():
        c = CONTRACTS[name]
        assert c.name == name
        assert c.endpoint.strip(), name
        assert c.consumer.strip(), name
        assert c.rules or c.custom is not None, name


def test_contract_dataclasses_are_frozen():
    c = CONTRACTS[names()[0]]
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.name = "mutated"          # type: ignore[misc]


def test_unknown_contract_name_is_an_error_not_a_silent_pass():
    with pytest.raises(ContractError) as exc:
        validate("no_such_provider", {})
    assert "未登记" in str(exc.value)
    with pytest.raises(ContractError):
        assert_contract("no_such_provider", {})


def test_every_contract_has_at_least_one_positive_fixture():
    missing = set(names()) - _fixture_contracts("ok")
    assert not missing, f"这些契约还没有正例 fixture: {sorted(missing)}"


def test_fixture_prefixes_never_reference_an_unregistered_contract():
    for sub in ("ok", "broken"):
        unknown = _fixture_contracts(sub) - set(names())
        assert not unknown, f"{sub} 里有未登记契约名的 fixture: {sorted(unknown)}"


# ── 路径探针与规则语义 ─────────────────────────────────────────────────

def test_missing_nested_field_is_reported_by_full_path():
    problems = validate("deepseek_chat", {"choices": [{"message": {"role": "assistant"}}]})
    assert any("choices[].message.content" in p for p in problems), problems


def test_array_wildcard_checks_every_element():
    ok = {"code": "Success",
          "data": {"status": "SUCCESS",
                   "results": [{"type": "video", "url": "https://a/1.mp4"},
                               {"type": "cover", "url": "https://a/1.jpg"}]}}
    assert validate("autodl_result", ok) == []

    bad = {"code": "Success",
           "data": {"status": "SUCCESS",
                    "results": [{"type": "video", "url": "https://a/1.mp4"},
                                {"type": "cover"}]}}
    problems = validate("autodl_result", bad)
    assert any("data.results[].url" in p for p in problems), problems


def test_when_condition_suppresses_rules_until_it_matches():
    # RUNNING 时还没有 results，这不算违约
    assert validate("autodl_result", {"code": "Success", "data": {"status": "RUNNING"}}) == []
    # SUCCESS 时 results[].url 就是硬要求
    assert validate("autodl_result", {"code": "Success", "data": {"status": "SUCCESS"}}) != []


def test_type_mismatch_names_expected_and_actual_type():
    problems = validate("deepseek_chat", {"choices": {"0": {}}})
    assert any("类型应为 list" in p and "dict" in p for p in problems), problems


def test_nonempty_rejects_blank_string():
    problems = validate("autodl_submit", {"code": "Success", "data": {"task_id": ""}})
    assert any("不能是空字符串" in p for p in problems), problems


def test_enum_rejects_an_unexpected_code():
    problems = validate("autodl_submit", {"code": "Fail", "data": {"task_id": "t"}})
    assert any("不在" in p for p in problems), problems


def test_optional_field_is_allowed_to_be_absent():
    # autodl_result 的 data.status / data.results 都是 required=False
    assert validate("autodl_result", {"code": "Success", "data": {}}) == []


def test_assert_contract_returns_the_payload_on_success():
    payload = {"choices": [{"message": {"content": "hi"}}]}
    assert assert_contract("deepseek_chat", payload) is payload


def test_assert_contract_collects_problems_into_the_error():
    with pytest.raises(ContractError) as exc:
        assert_contract("deepseek_chat", {"choices": []})
    err = exc.value
    assert err.name == "deepseek_chat"
    assert err.problems and any("content" in p for p in err.problems)
    assert "deepseek_chat" in str(err)


def test_is_valid_matches_validate_result():
    assert is_valid("autodl_submit", {"code": "Success", "data": {"task_id": "t"}})
    assert not is_valid("autodl_submit", {"code": "Success", "data": {}})


# ── 自定义校验器（Upload-Post 的多形状响应） ──────────────────────────

def test_uploadpost_status_accepts_results_platforms_or_plain_status():
    assert is_valid("uploadpost_status", {"results": {"tiktok": {"status": "completed"}}})
    assert is_valid("uploadpost_status", {"platforms": {"x": {"status": "queued"}}})
    assert is_valid("uploadpost_status", {"status": "completed"})


def test_uploadpost_status_rejects_garbage():
    assert not is_valid("uploadpost_status", {})
    assert not is_valid("uploadpost_status", ["completed"])
    assert not is_valid("uploadpost_status", {"results": {"tiktok": "completed"}})


def test_uploadpost_me_requires_string_identity_fields_when_present():
    assert is_valid("uploadpost_me", {"success": True, "profile": "ayh-main"})
    assert is_valid("uploadpost_me", {"success": True})          # 字段可缺席
    assert not is_valid("uploadpost_me", {"profile": 123})


# ── PostFlow CLI 契约与生产模块不漂移 ────────────────────────────────

def test_postflow_auth_markers_match_the_publish_module():
    from s6_publish import publish

    assert publish._AUTH_MARKERS == contracts.POSTFLOW_AUTH_MARKERS
    assert publish._is_auth_error("未登录") is postflow_is_auth_error("未登录")
    assert len(contracts.POSTFLOW_AUTH_MARKERS) >= 8


def test_postflow_auth_detection_is_case_insensitive():
    assert postflow_is_auth_error("401 Unauthorized")
    assert postflow_is_auth_error("Token Expired，请重新登录")
    assert not postflow_is_auth_error("")
    assert not postflow_is_auth_error("发布成功：https://www.douyin.com/video/1")
    assert postflow_is_auth_error("Cookie 已失效") is True


def test_postflow_required_flags_are_all_used_by_the_domestic_command():
    from s6_publish import publish

    src = inspect.getsource(publish.CliPublishAdapter._domestic)
    assert f"\"{contracts.POSTFLOW_SUBCOMMAND}\"" in src, src
    for flag in contracts.POSTFLOW_REQUIRED_FLAGS:
        assert f"\"{flag}\"" in src, f"国内发布命令缺少必需参数 {flag}"


def test_postflow_command_flags_extracts_only_switches():
    cmd = ["postflow.exe", "douyin", "upload-video", "--account", "a",
           "--video", "v", "--title", "t", "--desc", "d", "--tags", "x,y"]
    flags = postflow_command_flags(cmd)
    assert contracts.POSTFLOW_SUBCOMMAND in cmd
    assert set(contracts.POSTFLOW_REQUIRED_FLAGS) <= set(flags)
    assert "a" not in flags and "douyin" not in flags   # 只抽 flag，不抽值
