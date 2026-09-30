"""Phase 13 契约测试 —— 第三方响应 fixture 全量校验。

验收③要求"任意 provider contract fixture 改坏时测试明确失败"。这里把每一份
fixture 都做成一条独立用例，所以被改坏的那一份会**指名道姓**地红，而不是
在某条大测试里含糊地失败。

反例（broken/）是可执行的规格：它们记录的是"这些形状我们绝对不接受"。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.contracts import is_valid, names, postflow_is_auth_error, validate

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"


def _json_cases(sub: str):
    return [pytest.param(p, id=f"{sub}/{p.name}")
            for p in sorted((FIXTURES / sub).glob("*.json"))]


def _text_cases(sub: str):
    return [pytest.param(p, id=f"{sub}/{p.name}")
            for p in sorted((FIXTURES / sub).glob("*.txt"))]


OK_CASES = _json_cases("ok")
BROKEN_CASES = _json_cases("broken")
POSTFLOW_CASES = _text_cases("postflow")
POSTFLOW_IDS = [p.name for p in sorted((FIXTURES / "postflow").glob("*.txt"))]

# 这些文本样本必须被判成"凭据失效"，其余必须是普通结果
AUTH_EXPECTED = {"upload_auth_expired.txt"}

# 每个 provider 都要有反例，否则"改坏 fixture 就报警"的承诺不成立
REQUIRED_BROKEN = set(names())


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _contract_of(path: Path) -> str:
    return path.name.split(".")[0]


# ── 正例：必须全部合规 ─────────────────────────────────────────────────

@pytest.mark.parametrize("path", OK_CASES)
def test_positive_fixture_satisfies_its_contract(path):
    problems = validate(_contract_of(path), _load(path))
    assert problems == [], f"{path.name} 应当合规，却报出：{problems}"


# ── 反例：必须被明确拒绝，且理由点到字段 ──────────────────────────────

@pytest.mark.parametrize("path", BROKEN_CASES)
def test_broken_fixture_is_rejected(path):
    problems = validate(_contract_of(path), _load(path))
    assert problems, f"{path.name} 已被改坏，契约却放行了"
    assert all(p.strip() for p in problems)


@pytest.mark.parametrize("path", BROKEN_CASES)
def test_broken_fixture_fails_is_valid_too(path):
    assert is_valid(_contract_of(path), _load(path)) is False


# ── fixture 集合自身的完整性 ───────────────────────────────────────────

def test_fixture_sets_are_non_empty():
    assert OK_CASES and BROKEN_CASES and POSTFLOW_CASES


def test_every_contract_has_at_least_one_broken_counterexample():
    present = {_contract_of(p) for p in (FIXTURES / "broken").glob("*.json")}
    missing = REQUIRED_BROKEN - present
    assert not missing, f"这些契约还没有反例 fixture：{sorted(missing)}"


def test_fixtures_are_not_blank():
    for path in [*(FIXTURES / "ok").glob("*.json"), *(FIXTURES / "broken").glob("*.json")]:
        assert path.read_text(encoding="utf-8").strip(), path.name


# ── PostFlow CLI 文本样本 ──────────────────────────────────────────────

@pytest.mark.parametrize("path", POSTFLOW_CASES, ids=POSTFLOW_IDS)
def test_postflow_text_sample_classifies_correctly(path):
    text = path.read_text(encoding="utf-8")
    assert text.strip(), path.name
    detected = postflow_is_auth_error(text)
    if path.name in AUTH_EXPECTED:
        assert detected is True, f"{path.name} 应当判为凭据失效"
    else:
        assert detected is False, f"{path.name} 是普通结果，不该判成凭据失效"


def test_postflow_samples_cover_both_auth_and_normal_outcomes():
    outcomes = {p.name in AUTH_EXPECTED for p in (FIXTURES / "postflow").glob("*.txt")}
    assert outcomes == {True, False}
