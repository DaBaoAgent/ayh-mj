"""幂等指纹（Phase 4 必做任务 1）。

同一份"job + stage + prompt + refs + workflow"必须得到同一个 fingerprint：
  · 提交前算一次，落进 `provider_tasks`（与 attempts.fingerprint）；
  · 进程崩溃重启后，用同一个 fingerprint 去查表 —— 查到 task_id 就只 query，
    绝不第二次 create_task（Phase 4 验收场景 1）；
  · 内容变了（换 prompt / 换参考图 / 换 workflow）→ 指纹变 → 允许作为新任务提交，
    这是"确实不同"而不是"重复扣费"。
"""
from __future__ import annotations

import hashlib

FP_VERSION = "fp1"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ref_token(ref, root=None) -> str:
    """参考素材归一：统一正斜杠 + 文件 size（内容变了 size 通常会变）。"""
    s = str(ref).replace("\\", "/")
    try:
        from pathlib import Path
        p = Path(ref)
        if not p.is_absolute() and root is not None:
            p = Path(root) / p
        if p.is_file():
            return f"{s}|{p.stat().st_size}"
    except OSError:
        pass
    return s


def prompt_hash(prompt: str) -> str:
    return _sha(prompt or "")


def refs_hash(refs, *, root=None) -> str:
    tokens = [_ref_token(r, root=root) for r in (refs or [])]
    return _sha("\n".join(tokens))


def fingerprint(*, job_uid: str, stage: str, prompt: str = "", refs=(),
                workflow: str = "", extra=None, root=None) -> str:
    """job + stage + prompt hash + refs hash + workflow（+ 可选 extra）。"""
    parts = {
        "v": FP_VERSION,
        "job": str(job_uid or ""),
        "stage": str(stage or ""),
        "prompt": prompt_hash(prompt),
        "refs": refs_hash(refs, root=root),
        "workflow": str(workflow or ""),
        "extra": "" if extra is None else _sha(repr(sorted(extra.items()))
                                               if isinstance(extra, dict) else str(extra)),
    }
    canonical = "|".join(f"{k}={parts[k]}" for k in
                         ("v", "job", "stage", "prompt", "refs", "workflow", "extra"))
    return _sha(canonical)


def fingerprint_parts(*, job_uid: str, stage: str, prompt: str = "", refs=(),
                      workflow: str = "", extra=None, root=None) -> dict:
    """可追溯的指纹组成（写进 artifact / event metadata，便于复现与审计）。"""
    return {
        "fingerprint": fingerprint(job_uid=job_uid, stage=stage, prompt=prompt,
                                   refs=refs, workflow=workflow, extra=extra, root=root),
        "fp_version": FP_VERSION, "job_uid": job_uid, "stage": stage,
        "prompt_chars": len(prompt or ""), "prompt_hash": prompt_hash(prompt),
        "refs_hash": refs_hash(refs, root=root), "ref_count": len(list(refs or [])),
        "workflow": workflow,
    }
