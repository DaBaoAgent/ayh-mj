"""Phase 11 单测 —— CreativeDNA → 特征（计划任务 3）。

重点证明：20 个字段**一个不少**都成为可分析 feature；没有 DNA 的快照被显式丢弃。
"""
from __future__ import annotations

import json

import pytest

from lib.creative.dna import REQUIRED_FIELDS
from lib.creative.structures import structure_by_id
from lib.jobstore import store
from s7_learn import features
from tests.p7_support import dna_for
from tests.p11_support import load_corpus, materialize, write_dna

pytestmark = pytest.mark.unit


def test_all_twenty_dna_fields_are_analysable_features():
    assert tuple(REQUIRED_FIELDS) == features.FEATURE_FIELDS
    assert len(features.FEATURE_FIELDS) == 20
    assert len(features.CATEGORICAL_FIELDS) == 19
    assert features.MULTI_FIELDS == ("risk_flags",)
    assert set(features.CATEGORICAL_FIELDS) | set(features.MULTI_FIELDS) == set(features.FEATURE_FIELDS)


def test_feature_values_skips_empties_but_keeps_all_filled_fields():
    dna = features.CreativeDNA.from_dict(dna_for(structure_by_id("S_duo_conflict")))
    single, multi = features.feature_values(dna)
    assert len(single) == 19, "dna_for 填满 19 个单值字段"
    assert set(single) == set(features.CATEGORICAL_FIELDS)
    assert multi == {"risk_flags": []}


def test_feature_values_carries_risk_flags_as_multi_valued():
    dna = features.CreativeDNA.from_dict(
        {**dna_for(structure_by_id("S_duo_conflict")), "risk_flags": ["a", "b"]})
    single, multi = features.feature_values(dna)
    assert multi["risk_flags"] == ["a", "b"]
    assert "risk_flags" not in single


def test_load_dna_map_reads_only_planner_style_documents(tmp_state):
    root = tmp_state.parent
    write_dna(root, "LRN_A", "S_duo_conflict")
    (root / "state" / "creative" / "dna_BROKEN.json").write_text("{not json", encoding="utf-8")
    (root / "state" / "creative" / "dna_EMPTY.json").write_text(
        json.dumps({"uid": "EMPTY", "dna": {}}), encoding="utf-8")
    records = features.load_dna_map(root)
    assert set(records) == {"LRN_A"}
    assert records["LRN_A"].structure_id == "S_duo_conflict"
    assert records["LRN_A"].day == "2026-09-30"


def test_load_dna_map_can_be_restricted_to_requested_uids(tmp_state):
    root = tmp_state.parent
    write_dna(root, "LRN_A", "S_duo_conflict")
    write_dna(root, "LRN_B", "S_magic_loop")
    assert set(features.load_dna_map(root, uids=["LRN_B"])) == {"LRN_B"}


def test_join_samples_drops_rows_without_dna_and_reports_them(tmp_state):
    root = tmp_state.parent
    materialize(root, store, load_corpus())
    from s7_learn import collector, normalizer
    rows = collector.collect_from_store(store)
    normalized, _ = normalizer.normalize(rows)
    dna_map = features.load_dna_map(root, uids=[r["uid"] for r in rows])
    samples = features.join_samples(rows, dna_map, normalized=normalized)
    assert len(samples) == 15, "16 条快照里有 1 条没有 DNA，必须被丢弃"
    assert features.dropped_uids(rows, dna_map) == ["LRN_NODNA_01"]
    sample = next(s for s in samples if s.uid == "LRN_G1_01")
    assert sample.features["genre"] == "G1"
    assert sample.composite is not None
    assert sample.values("genre") == ["G1"]
    assert sample.values("risk_flags") == []
