"""发布服务（Phase 10 任务 2/3/4/5/8）。

把"发布"变成 canonical 生命周期里的一段，而不是另一套脚本状态：

    READY ──(gate 通过, real_publish=true)──▶ PUBLISHING ──▶ LEARNING ──▶ DONE
                    │                              │
                    │ 声明无法确认/合规不过          │ 部分平台失败
                    ▼                              ▼
                 BLOCKED                        PAUSED（可 resume 续发）

要点：
  · **幂等**：external_id = `<uid>:<platform>` + `publish_records` 唯一索引；重入不会重复发帖；
  · **按平台独立记录**：一个平台失败不抹掉另一个平台的成功；
  · **AUTH_EXPIRED 立即暂停该平台**（写 `state/publish_paused.json`），不循环登录、不反复发布；
  · **平台风控/验证码/账号异常 → REQUIRE_HUMAN**：同样暂停该平台并交人工，绝不换路子绕过；
  · **一条都没真发出去不许记 DONE**：平台暂停重入时停在 PAUSED（否则是伪成功）；
  · **real_publish=false 时只出计划，不改状态、不落记录** —— 幂等与安全都靠这条兜底。
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .. import packaging
from ..jobstore import JobState
from .errors import (
    NOT_READY,
    PLATFORM_PAUSED,
    PUBLISH_AUTH,
    PUBLISH_QUOTA,
    REQUIRE_HUMAN_PUBLISH,
    UNKNOWN_JOB,
)

# publish_records.status 取值（唯一声明处）
SUCCESS = "SUCCESS"
DRAFT = "DRAFT"
FAILED = "FAILED"
AUTH_EXPIRED = "AUTH_EXPIRED"
QUOTA_BLOCKED = "QUOTA_BLOCKED"
PAUSED_STATUS = "PLATFORM_PAUSED"
SKIPPED = "SKIPPED_IDEMPOTENT"
DRY_RUN = "DRY_RUN"
# 平台风控 / 验证码 / 账号异常（计划 §15.6）：不是"再试一次"能解决的失败，
# 只能暂停该平台并交人工 —— 与 AUTH_EXPIRED 同一处理（pause_platform），
# 但错误码是 REQUIRE_HUMAN_PUBLISH，语义是"人工确认"，不是"去重新登录"。
NEEDS_HUMAN = "REQUIRE_HUMAN"

OK_STATUSES = (SUCCESS, DRAFT)
BAD_STATUSES = (FAILED, AUTH_EXPIRED, QUOTA_BLOCKED, NEEDS_HUMAN)
NEUTRAL_STATUSES = (SKIPPED, PAUSED_STATUS)

AI_DISCLOSURE_LABEL = "AI 生成内容（本视频画面/配音由 AI 生成）"


class PublishAdapter(Protocol):
    """发布通道适配器（真实实现见 `s6_publish.publish.CliPublishAdapter`）。"""

    def publish(self, *, uid: str, job: dict, brief: dict, platform: str,
                copy: dict, mode: str) -> dict:  # pragma: no cover - protocol
        ...


@dataclass
class PublishOutcome:
    uid: str
    ok: bool
    job_status: str = ""
    results: list[dict] = field(default_factory=list)
    error_code: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return {"uid": self.uid, "ok": self.ok, "job_status": self.job_status,
                "error_code": self.error_code or None, "message": self.message,
                "results": self.results}


def _default_root() -> Path:
    from ..settings import get_settings
    return get_settings().root


def _default_quota(platform: str) -> tuple[bool, str]:
    from s6_publish import publish as publish_mod
    return publish_mod.check_quota(platform)


def _default_mark(platform: str) -> None:
    from s6_publish import publish as publish_mod
    publish_mod.mark_published(platform)


class PublishService:
    """READY → 发布 → DONE/PAUSED/BLOCKED 的唯一实现。"""

    def __init__(self, *, store=None, adapter: PublishAdapter | None = None,
                 root: str | Path | None = None, quota=None, mark_published=None,
                 sleep=None, inter_platform_gap: float = 0.0) -> None:
        if store is None:
            from ..jobstore import store as default_store
            store = default_store
        self.store = store
        self.adapter = adapter
        self.root = Path(root) if root is not None else _default_root()
        self.quota = quota or _default_quota
        self.mark_published = mark_published or _default_mark
        self.sleep = sleep or _time.sleep
        self.inter_platform_gap = float(inter_platform_gap or 0.0)

    # ── 只读 ───────────────────────────────────────────────────
    def targets(self, uid: str) -> list[str]:
        brief = packaging.load_brief(self.root, uid)
        if not brief:
            return []
        return [str(t.get("platform")) for t in (brief.get("targets") or []) if t.get("platform")]

    def published(self, uid: str) -> dict[str, str]:
        """已终态成功的平台 → {platform: status}（幂等依据）。"""
        out: dict[str, str] = {}
        for row in self.store.list_publishes(uid):
            status = str(row.get("status") or "")
            if status in OK_STATUSES:
                out[str(row.get("platform"))] = status
        return out

    def plan(self, uid: str, platforms: list[str] | None = None) -> dict:
        """演练：只出计划，不改任何状态、不落任何记录。"""
        job = self.store.get_job(uid)
        if job is None:
            return PublishOutcome(uid, False, error_code=UNKNOWN_JOB,
                                  message=f"任务不存在：{uid}").to_dict()
        brief = packaging.load_brief(self.root, uid)
        plats = list(platforms or self.targets(uid))
        gate = packaging.publish_gate(brief, platforms=plats)
        done = self.published(uid)
        return {
            "uid": uid, "ok": gate.ok, "dry_run": True, "job_status": job.get("status"),
            "platforms": plats, "gate": gate.to_dict(),
            "already_published": done,
            "items": [{"platform": p, "mode": self._mode_of(brief, p),
                       "skip": p in done}
                      for p in plats],
            "error_code": gate.code or None, "message": gate.message,
        }

    # ── 发布 ───────────────────────────────────────────────────
    def publish(self, uid: str, *, platforms: list[str] | None = None,
                real: bool | None = None) -> dict:
        job = self.store.get_job(uid)
        if job is None:
            return PublishOutcome(uid, False, error_code=UNKNOWN_JOB,
                                  message=f"任务不存在：{uid}").to_dict()
        status = str(job.get("status") or "")
        if status not in (JobState.READY, JobState.PUBLISHING):
            return PublishOutcome(uid, False, job_status=status, error_code=NOT_READY,
                                  message=f"任务状态是 {status}，不是 READY，不能发布").to_dict()

        brief = packaging.load_brief(self.root, uid)
        plats = list(platforms or self.targets(uid) or self._config_platforms(job))
        gate = packaging.publish_gate(brief, platforms=plats)

        if real is None:
            real = self._real_publish(job)
        if not real:
            return self.plan(uid, plats)

        if not gate.ok:
            self._block(uid, gate.code, gate.message)
            return PublishOutcome(uid, False, job_status=job.get("status"),
                                  error_code=gate.code, message=gate.message,
                                  results=[]).to_dict()

        if status == JobState.READY:
            self.store.transition(uid, JobState.PUBLISHING, stage="publish",
                                  message="发布 Gate 通过，开始按平台发布")

        results: list[dict] = []
        done = self.published(uid)
        for i, platform in enumerate(plats):
            results.append(self._publish_one(uid, job, brief, platform, done))
            if self.inter_platform_gap and i + 1 < len(plats):
                self.sleep(self.inter_platform_gap)

        return self._finalize(uid, results).to_dict()

    # ── 内部 ───────────────────────────────────────────────────
    def _config_platforms(self, job: dict) -> list[str]:
        snapshot = self._snapshot(job)
        plats = [str(p) for p in (snapshot.get("publish_platforms") or []) if p]
        return plats or ["douyin"]

    @staticmethod
    def _mode_of(brief: dict | None, platform: str) -> str:
        """演练路径要能如实报告"物料缺失"，绝不能因为 brief=None 直接崩。"""
        if not isinstance(brief, dict):
            return ""
        try:
            return str(packaging.materialize(brief, platform).get("mode") or "")
        except (KeyError, TypeError):
            return "unknown"

    @staticmethod
    def _snapshot(job: dict) -> dict:
        snapshot = job.get("config_snapshot")
        if isinstance(snapshot, str):
            import json
            try:
                snapshot = json.loads(snapshot)
            except ValueError:
                snapshot = {}
        return snapshot if isinstance(snapshot, dict) else {}

    def _real_publish(self, job: dict) -> bool:
        return bool(self._snapshot(job).get("real_publish", False))

    def _block(self, uid: str, code: str, message: str) -> None:
        self.store.add_event(uid, "publish_blocked", message[:400], stage="publish",
                             data={"error_code": code})
        job = self.store.get_job(uid) or {}
        if str(job.get("status")) in (JobState.READY, JobState.PUBLISHING):
            self.store.transition(uid, JobState.BLOCKED, stage="publish",
                                  message=message[:400], error_code=code)

    def _publish_one(self, uid: str, job: dict, brief: dict, platform: str,
                     done: dict[str, str]) -> dict:
        external_id = f"{uid}:{platform}"
        if platform in done:
            return {"platform": platform, "status": SKIPPED, "external_id": external_id,
                    "reason": f"该平台已发布过（{done[platform]}），幂等跳过"}

        reason = packaging.pause_reason(self.root, platform)
        if reason:
            return {"platform": platform, "status": PAUSED_STATUS, "external_id": external_id,
                    "reason": f"平台已暂停：{reason}"}

        ok, why = self.quota(platform)
        if not ok:
            self.store.record_publish(uid, platform, external_id=external_id,
                                      status=QUOTA_BLOCKED, error=why,
                                      ai_disclosure=AI_DISCLOSURE_LABEL)
            return {"platform": platform, "status": QUOTA_BLOCKED, "external_id": external_id,
                    "reason": why}

        if self.adapter is None:
            from s6_publish.publish import CliPublishAdapter
            self.adapter = CliPublishAdapter()

        copy = packaging.materialize(brief, platform)
        try:
            res = dict(self.adapter.publish(uid=uid, job=job, brief=brief, platform=platform,
                                            copy=copy, mode=copy["mode"]) or {})
        except Exception as exc:                      # 适配器异常也不能拖垮其他平台
            res = {"status": FAILED, "error": f"{type(exc).__name__}: {exc}"}

        status = str(res.get("status") or FAILED)
        if status in OK_STATUSES:
            self.mark_published(platform)
        elif status in (AUTH_EXPIRED, NEEDS_HUMAN):
            # 凭据失效 / 平台风控都要立刻熔断该平台：不许循环登录，也不许"换条路再试"。
            default = ("凭据失效（AUTH_EXPIRED）" if status == AUTH_EXPIRED
                       else "平台风控/验证码（REQUIRE_HUMAN）")
            packaging.pause_platform(self.root, platform,
                                     res.get("error") or default)

        self.store.record_publish(
            uid, platform, post_id=res.get("post_id"), post_url=res.get("post_url"),
            external_id=external_id, status=status, ai_disclosure=AI_DISCLOSURE_LABEL,
            error=res.get("error"))
        out = {"platform": platform, "status": status, "external_id": external_id,
               "mode": copy["mode"], "post_id": res.get("post_id"),
               "post_url": res.get("post_url")}
        if res.get("error"):
            out["reason"] = str(res["error"])[:300]
        if res.get("detail"):
            out["detail"] = res["detail"]
        return out

    def _finalize(self, uid: str, results: list[dict]) -> PublishOutcome:
        counts: dict[str, int] = {}
        for r in results:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        good = sum(counts.get(s, 0) for s in OK_STATUSES)
        bad = sum(counts.get(s, 0) for s in BAD_STATUSES)
        self.store.add_event(uid, "publish_done",
                             f"发布结果：成功 {good} / 失败 {bad}（{counts}）", stage="publish",
                             data={"counts": counts})
        if bad and not good:
            code = self._first_code(results)
            self.store.transition(uid, JobState.BLOCKED, stage="publish",
                                  message=f"全部平台发布失败（{counts}）", error_code=code)
            return PublishOutcome(uid, False, JobState.BLOCKED, results, code,
                                  f"全部平台发布失败：{counts}")
        if bad:
            self.store.transition(uid, JobState.PAUSED, stage="publish",
                                  message=f"部分平台成功，其余待重试（{counts}）")
            return PublishOutcome(uid, True, JobState.PAUSED, results, "",
                                  f"部分平台成功，其余待重试：{counts}")
        if counts.get(PAUSED_STATUS):
            # 平台被熔断暂停（AUTH_EXPIRED / 风控 / 声明无法确认）后重入：一条都没真发出去
            # 的时候**绝不能记成 DONE** —— 那是伪成功，会让 WebUI 与统计以为已发布过。
            # 停在 PAUSED，等人工解除暂停后再续发。
            code = "" if good else PLATFORM_PAUSED
            message = (f"部分平台处于暂停状态，未发布全部目标（{counts}）" if good
                       else f"平台处于暂停状态，未发布任何内容（{counts}）")
            self.store.transition(uid, JobState.PAUSED, stage="publish",
                                  message=message, error_code=code or None)
            return PublishOutcome(uid, good > 0, JobState.PAUSED, results, code, message)
        # 全绿（含草稿）→ 进学习层（Phase 11 会在这里落表现数据），再到 DONE
        self.store.transition(uid, JobState.LEARNING, stage="publish",
                              message=f"发布完成（{counts}），进入学习层")
        self.store.transition(uid, JobState.DONE, stage="publish",
                              message=f"任务完成（{counts}）")
        return PublishOutcome(uid, True, JobState.DONE, results, "", f"发布完成：{counts}")

    def _first_code(self, results: list[dict]) -> str:
        for r in results:
            status = r["status"]
            if status == AUTH_EXPIRED:
                return PUBLISH_AUTH
            if status == NEEDS_HUMAN:
                return REQUIRE_HUMAN_PUBLISH
            if status == QUOTA_BLOCKED:
                return PUBLISH_QUOTA
        return REQUIRE_HUMAN_PUBLISH if not results else FAILED


def outcome_of(result: dict) -> PublishOutcome:
    """把 to_dict() 的结果转回结构体（WebUI/CLI 复用）。"""
    return PublishOutcome(uid=str(result.get("uid") or ""), ok=bool(result.get("ok")),
                          job_status=str(result.get("job_status") or ""),
                          results=list(result.get("results") or []),
                          error_code=str(result.get("error_code") or ""),
                          message=str(result.get("message") or ""))


__all__ = [
    "AUTH_EXPIRED", "AI_DISCLOSURE_LABEL", "BAD_STATUSES", "DRAFT", "DRY_RUN", "FAILED",
    "NEEDS_HUMAN", "NEUTRAL_STATUSES", "OK_STATUSES", "PAUSED_STATUS", "PublishAdapter",
    "PublishOutcome", "PublishService", "QUOTA_BLOCKED", "SKIPPED", "SUCCESS",
    "outcome_of",
]
