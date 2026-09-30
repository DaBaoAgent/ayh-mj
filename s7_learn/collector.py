"""只读采集 / 导入平台表现（Phase 11 必做任务 1 / 2）。

铁律（计划 §Phase 11「指标模型」）：
  · 只有平台**实际提供**的指标才记录；取不到的字段一律 NULL，
    **禁止拿 0 冒充** —— 0 与"未知"在统计上完全不同：0 会拉低均值并伪造置信度；
  · 采集优先走官方 / 已有可信接口；需要浏览器时只做**低频只读**采集，
    不做任何激进反自动化绕过（本模块不含任何登录态伪造 / 指纹伪装 / 并发轰炸）。

只读：本模块不写平台，只把看到的数字搬进本地 `performance_metrics` 表。
"""
from __future__ import annotations

import json
from pathlib import Path

METRIC_FIELDS: tuple[str, ...] = (
    "impressions", "views", "skip_2s", "retention_5s", "avg_watch_time",
    "avg_watch_pct", "completion", "rewatches", "likes", "comments",
    "shares", "saves", "follows", "profile_visits", "dms", "conversion_proxy",
)

SNAPSHOT_FIELDS = ("uid", "platform", "post_id", "snapshot_time")


class CollectionRefused(RuntimeError):
    """采集被拒绝（无官方只读通道 / 参数非法）—— 拒绝，而不是偷偷绕过。"""


def clean_metrics(metrics: dict | None) -> dict:
    """只保留已知字段；None / 空串一律**丢弃**（丢 = 落库 NULL，不是 0）。"""
    out: dict = {}
    for key, value in (metrics or {}).items():
        if key not in METRIC_FIELDS:
            raise ValueError(f"未知指标 {key!r}（可用：{list(METRIC_FIELDS)}）")
        if value is None or value == "":
            continue
        out[key] = value
    return out


def snapshot_key(snapshot: dict) -> tuple:
    """同一 (uid, platform, post_id, snapshot_time) 只允许一条 —— 重复导入必须幂等。"""
    uid = snapshot.get("uid") or snapshot.get("job_uid") or ""
    return (str(uid), str(snapshot.get("platform") or ""),
            str(snapshot.get("post_id") or ""), str(snapshot.get("snapshot_time") or ""))


def normalize_snapshot(raw: dict) -> dict:
    """把一条原始快照规整成可落库的形状（缺时间戳 = 拒绝：结论必须能追到时间窗口）。"""
    snap = {
        "uid": str(raw.get("uid") or raw.get("job_uid") or ""),
        "platform": str(raw.get("platform") or "").strip().lower(),
        "post_id": (str(raw["post_id"]) if raw.get("post_id") else None),
        "snapshot_time": str(raw.get("snapshot_time") or ""),
        "metrics": clean_metrics(raw.get("metrics") or raw.get("raw") or {}),
    }
    if not snap["uid"] or not snap["platform"]:
        raise ValueError("snapshot 必须带 uid 与 platform")
    if not snap["snapshot_time"]:
        raise ValueError("snapshot_time 缺失 —— 学习结论必须能追到时间窗口")
    return snap


def existing_keys(store, uid: str | None = None) -> set:
    """库里已有的快照键（去重依据）。"""
    return {snapshot_key(row) for row in store.list_performance_metrics(uid)}


def import_snapshots(store, snapshots, *, dry_run: bool = False) -> dict:
    """幂等导入一批快照 → `performance_metrics`。

    返回 `{total, imported, skipped, errors}`；`skipped` 是"同一快照已存在"，
    `errors` 是形状非法的行（不静默吞掉）。
    """
    items = list(snapshots)
    seen = existing_keys(store)
    imported, skipped, errors = 0, 0, []
    for raw in items:
        try:
            snap = normalize_snapshot(raw)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        key = snapshot_key(snap)
        if key in seen:
            skipped += 1
            continue
        if not dry_run:
            store.add_performance_metric(
                snap["uid"], snap["platform"], post_id=snap["post_id"],
                snapshot_time=snap["snapshot_time"], raw=raw,
                **snap["metrics"])
        seen.add(key)
        imported += 1
    return {"total": len(items), "imported": imported,
            "skipped": skipped, "errors": errors}


def load_fixture(path: str | Path) -> list[dict]:
    """读一份 fixture（`.json` 数组 / 单对象 / `.jsonl`）→ 快照列表。"""
    text = Path(path).read_text(encoding="utf-8")
    if str(path).lower().endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    doc = json.loads(text)
    if isinstance(doc, dict) and "snapshots" in doc:
        return list(doc["snapshots"])
    return list(doc) if isinstance(doc, list) else [doc]


def collect_from_store(store, *, uid: str | None = None, platform: str | None = None,
                       since: str | None = None) -> list[dict]:
    """从本地库读快照（**只读**），并把指标压成"只有实际存在字段"的 dict。"""
    rows = store.list_performance_metrics(uid, platform=platform, since=since)
    out: list[dict] = []
    for row in rows:
        present = {f: row.get(f) for f in METRIC_FIELDS if row.get(f) is not None}
        out.append({
            "uid": row.get("job_uid") or "", "platform": row.get("platform") or "",
            "post_id": row.get("post_id"), "snapshot_time": row.get("snapshot_time") or "",
            "metrics": present, "missing": [f for f in METRIC_FIELDS if f not in present],
        })
    return out


def fetch_official(*, source: str, reader=None) -> list[dict]:
    """官方只读采集钩子 —— 没有可信通道就**拒绝**，绝不退化成浏览器绕过。

    `reader` 必须由调用方注入一个低频只读客户端（例如平台官方指标 API 的封装）。
    本函数不构造任何登录态、不启动浏览器、不并发轰炸。
    """
    if reader is None:
        raise CollectionRefused(
            f"未配置 {source} 的官方只读通道：Phase 11 不做绕过式采集。"
            "请改用 import_snapshots() 导入可信来源的表现快照"
            "（平台导出文件 / 人工录入 / 已授权的只读接口封装）。")
    return list(reader())
