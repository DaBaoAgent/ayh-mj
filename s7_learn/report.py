"""每日 / 每周复盘（Phase 11 必做任务 4 / 9）。

计划要求"每日生成 performance summary：genre/hook/angle/sales_point/cast/shot_pattern
的表现分布"，并且**每条学习结论都必须能追溯到样本量和时间窗口**。

所以这里每个数字都成组出现：
    value → {n, window_days, window, mean, smoothed, confidence}
没有 n 与窗口的结论在本模块里根本无法被表达 —— 结构上就杜绝了"凭感觉说某片型好"。
"""
from __future__ import annotations

import json
from pathlib import Path

from .scorer import (
    CONFIDENCE_LOW,
    CONFIDENCE_ORDER,
    NO_PREDICTION_NOTE,
    PerformanceModel,
    learn,
)

# 计划点名的六个维度 + 其余可分析维度（DNA 字段名与计划中文名的对应见 README/验收文档）
SUMMARY_FIELDS: tuple[str, ...] = (
    "genre", "hook_type", "angle", "sales_point", "cast_pattern", "shot_pattern",
    "audience", "conflict_type", "visual_motif", "dialogue_mode",
)

# 计划里的中文名 → DNA 字段名（报告里两种叫法都出现，避免读报告的人对不上号）
FIELD_LABELS: dict[str, str] = {
    "genre": "片型 genre", "hook_type": "钩子 hook", "angle": "叙事思路 angle",
    "sales_point": "卖点 sales_point", "cast_pattern": "角色组合 cast",
    "shot_pattern": "镜头结构 shot_pattern", "audience": "受众 audience",
    "conflict_type": "冲突类型 conflict", "visual_motif": "视觉母题 motif",
    "dialogue_mode": "台词模式 dialogue",
}

LEARN_DIR = ("state", "learn")


def learn_dir(root: str | Path) -> Path:
    path = Path(root).joinpath(*LEARN_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def field_distribution(model: PerformanceModel, field_name: str, *, min_n: int = 3) -> list[dict]:
    """某维度的表现分布（按平滑分降序）。`n < min_n` 的取值**照样列出**但标 low confidence。"""
    cells = list((model.cells.get(field_name) or {}).values())
    rows = [c.to_dict() for c in cells]
    rows.sort(key=lambda r: (r["smoothed"], CONFIDENCE_ORDER.get(r["confidence"], 0), r["n"]),
              reverse=True)
    for row in rows:
        row["low_n"] = row["n"] < int(min_n)
    return rows


def summarize(model: PerformanceModel, samples=None, *, day: str = "", window_days: int = 30,
              top_n: int = 8, fields=None) -> dict:
    """把模型压成一份可读复盘：逐维度分布 + 全库基线与置信度。"""
    used_fields = tuple(fields or SUMMARY_FIELDS)
    distributions = {}
    for field_name in used_fields:
        rows = field_distribution(model, field_name)
        distributions[field_name] = {
            "label": FIELD_LABELS.get(field_name, field_name),
            "values": rows[: max(1, int(top_n))],
            "value_count": len(rows),
        }
    total = len(samples) if samples is not None else model.n_samples
    return {
        "day": day, "window_days": int(window_days), "window": dict(model.window),
        "samples_total": total, "samples_used": model.n_samples,
        "dropped_uids": list(model.dropped_uids),
        "global_mean": model.global_mean, "confidence": model.confidence(),
        "low_confidence": model.confidence() == CONFIDENCE_LOW,
        "platforms": list(model.platforms),
        "distributions": distributions,
        "conclusion_rule": ("每条结论都带 n 与时间窗口；n 低于中置信阈值一律标注 low confidence，"
                           "不据此淘汰任何片型"),
        "note": NO_PREDICTION_NOTE,
    }


def render_markdown(summary: dict) -> str:
    """人类可读报告（与 JSON 同一份数据，绝不各算一份）。"""
    lines = [
        f"# 表现复盘 {summary.get('day') or '(未指定日期)'}",
        "",
        f"- 样本：{summary.get('samples_used')}/{summary.get('samples_total')} 条可用"
        f"（丢弃 {len(summary.get('dropped_uids') or [])} 条无 DNA 的快照）",
        f"- 时间窗口：近 {summary.get('window_days')} 天"
        f"（{(summary.get('window') or {}).get('start', '')[:10]}"
        f" ～ {(summary.get('window') or {}).get('end', '')[:10]}）",
        f"- 全库均值：{_fmt(summary.get('global_mean'))}；整体置信度：{summary.get('confidence')}"
        + ("（**数据不足：low confidence**）" if summary.get("low_confidence") else ""),
        f"- 平台：{'、'.join(summary.get('platforms') or []) or '（无）'}",
        "",
        f"> {summary.get('note', '')}",
        f"> {summary.get('conclusion_rule', '')}",
    ]
    for field_name, block in (summary.get("distributions") or {}).items():
        lines += ["", f"## {block.get('label', field_name)}（{block.get('value_count', 0)} 个取值）", "",
                  "| 取值 | n | 窗口(天) | 均值 | 平滑 | 置信度 |", "|---|---|---|---|---|---|"]
        values = block.get("values") or []
        if not values:
            lines.append("| （无样本） | 0 | - | - | - | low |")
        for row in values:
            flag = " ⚠样本少" if row.get("low_n") else ""
            lines.append(f"| {row['value']}{flag} | {row['n']} | {row['window_days']} | "
                         f"{_fmt(row['mean'])} | {_fmt(row['smoothed'])} | {row['confidence']} |")
    return "\n".join(lines) + "\n"


def _fmt(value) -> str:
    return "-" if value is None else f"{float(value):.3f}"


def write_summary(root: str | Path, summary: dict, *, name: str | None = None) -> dict:
    """落 `state/learn/<name>.json` + `.md`（JSON 与 MD 同一份数据）。"""
    base = learn_dir(root)
    stem = name or f"summary_{summary.get('day') or 'latest'}"
    json_path = base / f"{stem}.json"
    md_path = base / f"{stem}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def build_summary(samples, *, day: str = "", window_days: int = 30, prior_n: float = 5.0,
                  min_medium: int = 8, min_high: int = 30, dropped_uids=None,
                  top_n: int = 8, fields=None) -> tuple[dict, PerformanceModel]:
    """样本 → (复盘 dict, 模型)。模型一并返回，供 Planner 复用同一次学习。"""
    model = learn(samples, window_days=window_days, prior_n=prior_n, min_medium=min_medium,
                  min_high=min_high, dropped_uids=dropped_uids)
    summary = summarize(model, samples, day=day, window_days=window_days, top_n=top_n,
                        fields=fields)
    return summary, model


def daily_summary(samples, root, *, day: str = "", window_days: int = 30, prior_n: float = 5.0,
                  min_medium: int = 8, min_high: int = 30, dropped_uids=None) -> dict:
    """每日复盘：学习 → 汇总 → 落盘（`state/learn/summary_<day>.json|.md`）。"""
    summary, _model = build_summary(
        samples, day=day, window_days=window_days, prior_n=prior_n,
        min_medium=min_medium, min_high=min_high, dropped_uids=dropped_uids)
    summary["paths"] = write_summary(root, summary)
    return summary


def weekly_summary(samples, root, *, week: str, window_days: int = 7, **kwargs) -> dict:
    """每周复盘：同一套逻辑，窗口默认 7 天，落 `summary_week_<week>`。"""
    summary, _model = build_summary(samples, day=week, window_days=window_days, **kwargs)
    summary["period"] = "week"
    summary["paths"] = write_summary(root, summary, name=f"summary_week_{week}")
    return summary
