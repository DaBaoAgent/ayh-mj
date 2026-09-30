"""Phase 6 —— 卖点池的唯一事实来源是 Claims Registry（验收标准①）。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from lib import claims as claims_mod
from lib import products

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

# 参数口径（数字 + 单位）。排除 `light_13.8` / `remote_15m` 这类标识符：
# 前后紧邻 [A-Za-z0-9_.] 的都不算（`_` 把 id 和数字连在一起）。
_PARAM = re.compile(
    r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?\s*"
    r"(?:kg|公斤|千克|公里|千米|km|cm|公分|厘米|度|股|项|年|天|分钟|%|安|瓦|米|斤)"
    r"(?![A-Za-z0-9_])")


def test_products_source_holds_no_product_parameter_literal():
    """同一参数只能有一个权威机器可读来源：lib/products.py 不得再内置口径。"""
    src = (ROOT / "lib" / "products.py").read_text(encoding="utf-8")
    hits = sorted(set(_PARAM.findall(src)))
    assert hits == [], f"lib/products.py 又出现了内置参数口径：{hits}"


def test_sales_points_are_materialized_from_the_registry():
    reg = claims_mod.load()
    assert products.SALES_POINTS
    for point in products.SALES_POINTS:
        assert point["claim_ids"], point
        for cid in point["claim_ids"]:
            assert reg.get(cid) is not None, f"{point['id']} 引用了未登记 claim {cid}"


def test_hook_comes_from_the_registry_only_when_usable():
    reg = claims_mod.load()
    for point in products.SALES_POINTS:
        if point["usable"]:
            primary = reg.get(point["claim_ids"][0])
            assert point["hook"] == primary.display_text, point
        else:
            assert point["hook"] == "", point


def test_unusable_points_stay_in_the_pool_but_are_marked(tmp_state):
    unusable = {p["id"]: p for p in products.SALES_POINTS if not p["usable"]}
    assert {"shock_18", "range_39", "lithium_safe"} <= set(unusable)
    for point in unusable.values():
        assert point["blocked"], point


def test_next_point_never_returns_an_unusable_point(tmp_state):
    for template in list(products.TEMPLATE_FIT) + [""]:
        point = products.next_point(template)
        assert point["usable"], (template, point)


def test_point_to_claim_mapping_is_explicit_for_multi_claim_points():
    assert products.claim_ids_for("warranty_life") == ["warranty_frame_life", "warranty_motor_2y"]
    assert products.claim_ids_for("auto_stop") == ["auto_stop"]
    assert products.claim_ids_for("") == []
    assert products.is_usable("auto_stop")
    assert not products.is_usable("shock_18")
    assert not products.is_usable("auto_stop", "no_such_channel")


def test_point_facts_never_leak_a_blocked_parameter():
    assert products.point_facts("shock_18") == ""
    assert products.point_facts("range_39") == ""
    assert "30" in products.point_facts("anti_flip")


def test_sales_points_brief_is_the_registry_facts_block():
    block = claims_mod.load().facts_block("script")
    assert products.sales_points_brief(120) == block[:120]
    assert "30" in products.sales_points_brief()
