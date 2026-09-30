"""prescreen（Phase 7 必做任务 11/12）—— 高风险新构图先花 1/3 的钱试拍。

判据来自计划：多人、复杂交互、特殊道具、品牌字、危险形变动作。
判定结果：
  · `risk_of(spec)` → {score, level, reasons}；
  · `needs_prescreen(spec)` → 高风险（或中等风险 + 用了没拍过的骨架）才 True；
  · `build_prescreen_spec(spec, shot_no, seconds)` → 5s 预筛 spec（与 tools/prescreen 同口径，
    这里才是唯一实现，CLI 只是调用方）；
  · `record_prescreen(store, uid, passed=...)` → 结论写进 evaluations（任务 12）。

对外只暴露"要不要预筛"，绝不把"预筛通过"当默认值 —— 没跑过就是没通过。
"""
from __future__ import annotations

import re

# ── 风险规则：(标签, 权重, 判据) ────────────────────────────────
MANY_PEOPLE = 3                      # 同框 3 人以上才算"多人"
RISK_HIGH = 0.66
RISK_MEDIUM = 0.33
PRESCREEN_SECONDS = 5
PRESCREEN_EVAL = "prescreen"

_SHOT_RE = re.compile(r"\[Shot\s+\d+[^\]]*\]")


def _slots(spec) -> list[str]:
    pattern = str(_dna(spec).get("cast_pattern") or "")
    return [s for s in pattern.split("+") if s.strip()]


def _dna(spec) -> dict:
    if isinstance(spec, dict):
        return dict(spec.get("creative", {}).get("dna") or spec.get("dna") or {})
    return getattr(spec, "dna", None).to_dict() if getattr(spec, "dna", None) else {}


def _structure_id(spec) -> str:
    if isinstance(spec, dict):
        return str(spec.get("creative", {}).get("structure")
                   or spec.get("structure_id") or "")
    return str(getattr(spec, "structure_id", "") or "")


def risk_of(spec, *, seen_structures: tuple[str, ...] | list[str] = ()) -> dict:
    """高风险构图打分（0..1+）。reason 是给人看的，score 是给门禁用的。"""
    dna = _dna(spec)
    slots = _slots(spec)
    reasons: list[tuple[str, float]] = []

    n_people = len(slots)
    if n_people >= MANY_PEOPLE:
        reasons.append((f"同框 {n_people} 人（多人口型/一致性风险）", 0.3))

    if str(dna.get("dialogue_mode") or "") == "街访问答":
        reasons.append(("街访问答：路人插话 + 同时反应，交互复杂", 0.15))

    motif = str(dna.get("visual_motif") or "")
    if motif in ("后备箱装车", "坡道爬升"):
        reasons.append((f"特殊交互调度（{motif}）：人与产品的接触点容易崩", 0.2))
    if motif in ("老照片对比", "雨夜灯光"):
        reasons.append((f"特殊道具/光效（{motif}）", 0.15))
    if motif in ("折叠收放", "遥控轨迹"):
        reasons.append((f"危险形变动作（{motif}）：结构容易软掉/穿模", 0.3))

    if str(dna.get("conflict_type") or "") == "身体不便":
        reasons.append(("身体状态设定：模型容易删腿/画成悬空", 0.3))

    if str(dna.get("CTA") or "").strip():
        reasons.append(("有品牌字/收口句：画面文字与品牌字必须有正确字形", 0.15))

    sid = _structure_id(spec)
    if sid and sid not in set(seen_structures or ()):
        reasons.append((f"没拍过的骨架（{sid}）：构图/调度没有历史成功率", 0.2))

    score = round(sum(w for _, w in reasons), 3)
    level = "high" if score >= RISK_HIGH else ("medium" if score >= RISK_MEDIUM else "low")
    return {"score": score, "level": level,
            "reasons": [{"label": label, "weight": w} for label, w in reasons],
            "people": n_people, "structure": sid}


def needs_prescreen(spec, *, seen_structures: tuple[str, ...] | list[str] = ()) -> bool:
    """只有高风险才必须预筛（低风险直接进付费生成，不浪费一轮 5s 的钱）。"""
    return risk_of(spec, seen_structures=seen_structures)["level"] == "high"


def build_prescreen_spec(spec: dict, *, shot_no: int = 1,
                         seconds: int = PRESCREEN_SECONDS) -> dict:
    """从已编译的 prompt 里抽出第 shot_no 镜 → 5s 预筛 spec（其余原样保留）。"""
    prompt = str(spec.get("prompt") or "")
    if not prompt:
        raise ValueError("预筛需要已编译的 prompt（先跑 PromptCompiler）")
    marks = list(_SHOT_RE.finditer(prompt))
    if not marks:
        raise ValueError("prompt 里没有 [Shot N, ...] 段，无法抽镜")
    if not 1 <= shot_no <= len(marks):
        raise ValueError(f"该片只有 {len(marks)} 镜，取不到第 {shot_no} 镜")
    start = marks[shot_no - 1].start()
    end = marks[shot_no].start() if shot_no < len(marks) else len(prompt)
    pre, shot, tail = prompt[:start], prompt[start:end], prompt[end:]
    shot = _SHOT_RE.sub(f"[Shot 1, 0 to {seconds} seconds]", shot, count=1)
    shot = shot.replace("Hard cut.", "").replace("Hard cut", "").strip()
    uid = str(spec.get("job_uid") or spec.get("uid") or "")
    return {**spec,
            "job_uid": f"{uid}_shot{shot_no}",
            "duration": int(seconds),
            "prompt": "\n\n".join([pre, shot, tail] if tail.strip() else [pre, shot]),
            "prescreen_of": uid, "prescreen_shot": int(shot_no),
            "prescreen_seconds": int(seconds)}


def record_prescreen(store, uid: str, *, passed: bool, detail: dict | None = None,
                     stage: str = "preflight") -> None:
    """把预筛结论写进 evaluations（任务 12）；只有 passed=True 才放行 15s 正式片。"""
    store.add_evaluation(uid, PRESCREEN_EVAL, stage=stage, passed=bool(passed),
                         detail=dict(detail or {}))


def prescreen_passed(store, uid: str) -> bool:
    """查有没有一条 passed=True 的预筛结论（没有 = 没通过，绝不放行）。"""
    try:
        rows = store.list_evaluations(uid, PRESCREEN_EVAL)
    except Exception:
        return False
    return any(bool(r.get("passed")) for r in rows)
