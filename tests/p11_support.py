"""Phase 11 测试共享工具 —— 把 fixture 变成 DNA 文档 + 表现快照。

只做两件只读/写本地的事：按 Planner 同口径写 `state/creative/dna_<uid>.json`，
把 fixture 里的表现快照幂等导入 `performance_metrics`。全程不联网、不付费。
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.creative.structures import structure_by_id
from s7_learn import collector
from tests.p7_support import dna_for

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "performance"
CORPUS = FIXTURES / "corpus.json"
FLAT = FIXTURES / "snapshots.json"


def load_corpus(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or CORPUS).read_text(encoding="utf-8"))


def load_flat(path: str | Path | None = None) -> list[dict]:
    return list(json.loads(Path(path or FLAT).read_text(encoding="utf-8"))["snapshots"])


def flat_snapshots(corpus: dict) -> list[dict]:
    """把 corpus 摊平成 `collector` 认的快照列表（每条带上 uid）。"""
    return [dict(snap, uid=job["uid"]) for job in corpus["jobs"] for snap in job["snapshots"]]


def write_dna(root: str | Path, uid: str, structure_id: str, *,
              day: str = "2026-09-30", **overrides) -> Path:
    """写一份与 Planner 落盘同口径的 DNA 文档（学习层的唯一事实来源）。"""
    structure = structure_by_id(structure_id)
    dna = dna_for(structure)
    dna.update(overrides)
    path = Path(root) / "state" / "creative" / f"dna_{uid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "uid": uid, "day": day, "structure": structure_id,
        "structure_name": structure["name"], "dna": dna,
        "scores": {}, "rationale": {}, "claim_ids": [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def materialize(root: str | Path, store, corpus: dict | None = None, *,
                dry_run: bool = False) -> dict:
    """fixture → DNA 文档 + job + performance_metrics（幂等）。"""
    data = corpus or load_corpus()
    for job in data["jobs"]:
        if store.get_job(job["uid"]) is None:
            store.create_job(goal="学习样本", uid=job["uid"])
        if job.get("structure_id"):
            write_dna(root, job["uid"], job["structure_id"],
                      day=job.get("day") or data.get("day") or "2026-09-30")
    imported = collector.import_snapshots(store, flat_snapshots(data), dry_run=dry_run)
    return {"jobs": len(data["jobs"]), **imported}
