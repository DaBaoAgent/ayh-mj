"""CreativeDNA → 可分析 feature（Phase 11 必做任务 3）。

计划要求"CreativeDNA 全部成为可分析 feature"：20 个字段**一个都不排除**，
其中 `risk_flags` 是列表（多值 feature），其余 19 个是单值分类 feature。

特征数据来自 Planner 落盘的 `state/creative/dna_<uid>.json`（唯一事实来源），
这里只读它，不重新推导 DNA（否则"学习用的基因"和"生产用的基因"会对不上）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lib.creative.dna import REQUIRED_FIELDS, CreativeDNA

# 20 个字段全部可分析（计划任务 3）
FEATURE_FIELDS: tuple[str, ...] = tuple(REQUIRED_FIELDS)
# 单值分类特征（risk_flags 是多值，单独处理）
CATEGORICAL_FIELDS: tuple[str, ...] = tuple(f for f in FEATURE_FIELDS if f != "risk_flags")
MULTI_FIELDS: tuple[str, ...] = ("risk_flags",)

DNA_FILENAME = "dna_{uid}.json"


@dataclass
class DnaRecord:
    """一条 DNA 记录：基因 + 骨架 id + 规划日期（都来自 planner 的落盘）。"""

    uid: str
    dna: CreativeDNA
    structure_id: str = ""
    day: str = ""

    def to_dict(self) -> dict:
        return {"uid": self.uid, "structure_id": self.structure_id, "day": self.day,
                "dna": self.dna.to_dict()}


@dataclass
class Sample:
    """一条"视频 × 平台 × 快照"的学习样本：DNA + 标准化表现。"""

    uid: str
    platform: str
    post_id: str | None
    snapshot_time: str
    composite: float | None
    norm: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    multi_features: dict = field(default_factory=dict)
    structure_id: str = ""
    day: str = ""

    def values(self, field_name: str) -> list[str]:
        if field_name in MULTI_FIELDS:
            return [str(v) for v in (self.multi_features.get(field_name) or [])]
        value = self.features.get(field_name)
        return [str(value)] if value not in (None, "") else []

    def to_dict(self) -> dict:
        return {"uid": self.uid, "platform": self.platform, "post_id": self.post_id,
                "snapshot_time": self.snapshot_time, "structure_id": self.structure_id,
                "day": self.day, "composite": self.composite, "features": dict(self.features),
                "multi_features": dict(self.multi_features),
                "structure": self.features.get("shot_pattern", "")}


def dna_of(doc: dict | None) -> CreativeDNA | None:
    """从 `dna_<uid>.json` 的内容造 CreativeDNA（缺失/非法一律 None，不猜）。"""
    payload = (doc or {}).get("dna") if isinstance(doc, dict) else None
    if not isinstance(payload, dict) or not payload:
        return None
    try:
        return CreativeDNA.from_dict(payload)
    except (TypeError, ValueError):
        return None


def load_dna_map(root: str | Path, *, uids=None) -> dict[str, DnaRecord]:
    """读 `state/creative/dna_<uid>.json` → {uid: DnaRecord}（只读，缺文件就跳过）。"""
    base = Path(root) / "state" / "creative"
    wanted = set(uids) if uids else None
    out: dict[str, DnaRecord] = {}
    if not base.is_dir():
        return out
    for path in sorted(base.glob("dna_*.json")):
        uid = path.stem[len("dna_"):]
        if wanted is not None and uid not in wanted:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dna = dna_of(doc)
        if dna is None:
            continue
        out[uid] = DnaRecord(uid=uid, dna=dna,
                             structure_id=str(doc.get("structure") or ""),
                             day=str(doc.get("day") or ""))
    return out


def feature_values(dna: CreativeDNA) -> tuple[dict, dict]:
    """→ (单值特征 dict, 多值特征 dict)。空值不进 dict（空 ≠ 某个取值）。"""
    single: dict = {}
    for name in CATEGORICAL_FIELDS:
        value = getattr(dna, name, "")
        if value not in (None, ""):
            single[name] = str(value)
    multi = {"risk_flags": [str(f) for f in (dna.risk_flags or []) if str(f)]}
    return single, multi


def join_samples(rows: list[dict], dna_map: dict[str, DnaRecord], *,
                 normalized=None) -> list[Sample]:
    """把表现快照与 DNA 对齐成学习样本。

    **没有 DNA 的快照必须丢弃**（记进 `dropped`）—— 没有基因就没法回答"哪种片型更好"，
    硬塞一条空 DNA 只会污染特征分布。
    """
    by_uid = {r.uid: r for r in (normalized or [])}
    samples: list[Sample] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        record = dna_map.get(uid)
        if record is None:
            continue
        single, multi = feature_values(record.dna)
        norm_row = by_uid.get(uid)
        samples.append(Sample(
            uid=uid, platform=str(row.get("platform") or ""), post_id=row.get("post_id"),
            snapshot_time=str(row.get("snapshot_time") or ""),
            composite=(norm_row.composite if norm_row is not None else None),
            norm=dict(norm_row.norm if norm_row is not None else {}),
            metrics=dict(row.get("metrics") or {}), features=single, multi_features=multi,
            structure_id=record.structure_id, day=record.day))
    return samples


def dropped_uids(rows: list[dict], dna_map: dict[str, DnaRecord]) -> list[str]:
    """被丢掉（没有 DNA）的 uid 清单 —— 报告里必须显式说出来，不静默丢样本。"""
    return sorted({str(r.get("uid") or "") for r in rows
                   if str(r.get("uid") or "") and str(r.get("uid") or "") not in dna_map})
