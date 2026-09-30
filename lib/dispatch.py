"""队列派发缓存（Phase 2）。

`state/queue_15s/*.json` 只是"待执行 spec 的分发缓存"；任务事实在 JobStore 里。
  · 每个 spec 的内容 sha256 作为 fingerprint：同一份 spec 不会重复建 job；
  · job uid 直接沿用 spec 文件名 stem，保证与 out/gen_<uid>/ 归档目录一一对应；
  · 删除/重建 queue 目录不会影响 JobStore 已登记的任务。
"""
from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

from .jobstore import JobStore, sha256_of
from .jobstore import store as default_store


def spec_fingerprint(spec: Path | str) -> str:
    return sha256_of(Path(spec).read_bytes())


def _goal_from_spec(spec: Path) -> str:
    with suppress(OSError, ValueError):
        data = json.loads(spec.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in ("goal", "topic", "title", "idea"):
                if data.get(key):
                    return str(data[key])
    return f"queue:{spec.stem}"


def sync_queue(queue_dir: Path | str, *, store: JobStore | None = None) -> dict[str, str]:
    """把 queue 目录里的 spec 登记进 JobStore；返回 {uid: spec路径}。幂等。"""
    st = store or default_store
    queue_dir = Path(queue_dir)
    out: dict[str, str] = {}
    if not queue_dir.is_dir():
        return out
    for spec in sorted(queue_dir.glob("*.json")):
        if not spec.is_file():
            continue
        uid = spec.stem
        fingerprint = spec_fingerprint(spec)
        existing = st.get_job(uid)
        if existing is None:
            st.create_job(goal=_goal_from_spec(spec), uid=uid, fingerprint=fingerprint)
            st.add_artifact(uid, "spec", spec, stage="planning")
        elif existing.get("fingerprint") != fingerprint:
            st.set_fields(uid, fingerprint=fingerprint)
            st.add_artifact(uid, "spec", spec, stage="planning")
            st.add_event(uid, "spec_updated", f"spec 内容变化：{spec.name}")
        out[uid] = str(spec)
    return out
