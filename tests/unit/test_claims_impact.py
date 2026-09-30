"""Phase 6 —— 口径影响面分析：改了事实层要知道哪些内容受影响（任务 8）。"""
from __future__ import annotations

import pytest

from lib import claims as claims_mod

pytestmark = pytest.mark.unit


def test_impact_finds_the_code_that_quotes_a_claim():
    hits = claims_mod.impact("light_13.8")
    assert hits
    files = {h["file"] for h in hits}
    assert "lib/products.py" in files
    assert "s6_publish/engage.py" in files
    assert "assets/products/claims.yaml" in files


def test_impact_hit_shape_is_stable():
    for hit in claims_mod.impact("anti_flip"):
        assert set(hit) == {"file", "line", "token", "text"}
        assert isinstance(hit["line"], int) and hit["line"] >= 1
        assert hit["text"] and len(hit["text"]) <= 200


def test_impact_includes_forbidden_rewrites_so_stale_copy_is_caught():
    """禁用改写也必须能被检索出来，否则旧文案会漏网。"""
    hits = claims_mod.impact("light_13.8")
    lookup = " ".join(f"{h['token']} {h['text']}" for h in hits)
    assert "20kg" in lookup
    shock = " ".join(f"{h['token']} {h['text']}" for h in claims_mod.impact("shock_18"))
    assert "护脊" in shock


def test_impact_summary_aggregates_by_file():
    summary = claims_mod.impact_summary("anti_flip")
    assert summary["claim_id"] == "anti_flip"
    assert summary["files"] == len(summary["by_file"])
    assert summary["hits"] == sum(summary["by_file"].values())
    assert summary["files"] > 0
    assert all(v >= 1 for v in summary["by_file"].values())


def test_unknown_claim_id_is_a_hard_error():
    with pytest.raises(KeyError):
        claims_mod.impact("no_such_claim_id")


def test_impact_can_be_scoped_to_one_root(tmp_path, monkeypatch):
    monkeypatch.setattr(claims_mod, "ROOT", tmp_path)
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "old_copy.py").write_text("HOOK = '13.8kg，单手可拎'\n", encoding="utf-8")
    (lib / "unrelated.py").write_text("VALUE = 1\n", encoding="utf-8")
    hits = claims_mod.impact("light_13.8", roots=[lib])
    assert [h["file"] for h in hits] == ["lib/old_copy.py"]


def test_max_hits_caps_the_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(claims_mod, "ROOT", tmp_path)
    lib = tmp_path / "lib"
    lib.mkdir()
    body = "\n".join("x = '13.8kg'" for _ in range(50))
    (lib / "many.py").write_text(body + "\n", encoding="utf-8")
    assert len(claims_mod.impact("light_13.8", roots=[lib], max_hits=5)) == 5
