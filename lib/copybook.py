"""短剧结构库 — 爆款文案结构智能调用

每次文案生成（adapt_lines/脚本）自动注入结构要点：
  时间节拍 / 爽点类型 / 台词规则 / 检查清单
另供桥段库（bridges.jsonl，每日 2 点 cron 刷新）：
  短剧桥段 / 同行爆款 / 跨赛道爆款 — 未用优先、注入轮换
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRUCT_DIR = ROOT / "assets" / "scripts"
BRIDGES = STRUCT_DIR / "bridges.jsonl"


def structure_brief(max_chars: int = 2200) -> str:
    """短剧结构知识库摘要（供 LLM 文案生成智能调用）"""
    p = STRUCT_DIR / "drama_structures.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    # 去掉文档头部说明（来源行）
    lines = [ln for ln in text.splitlines() if not ln.startswith(">")]
    return "\n".join(lines)[:max_chars]


def _load_bridges() -> list[dict]:
    if not BRIDGES.exists():
        return []
    out = []
    for ln in BRIDGES.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _save_bridges(recs: list[dict]) -> None:
    BRIDGES.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                       encoding="utf-8")


def bridges_brief(limit: int = 8) -> str:
    """桥段库摘要（未注入优先+日期新优先，注入后自动轮换）"""
    recs = _load_bridges()
    if not recs:
        return ""
    recs.sort(key=lambda r: (r.get("injected", 0), -int(str(r.get("date", "")).replace("-", "") or 0)))
    top = recs[:limit]
    lines = ["【最新桥段库（从中选 0-2 条化用到台词创作，优先从未用过的）】"]
    for r in top:
        tags = "+".join(r.get("tags", [])[:3])
        lines.append(f"  · [{tags}] {r['title'][:52]}")
    # 注入轮换计数
    for r in recs:
        if r in top:
            r["injected"] = r.get("injected", 0) + 1
    _save_bridges(recs)
    return "\n".join(lines)


if __name__ == "__main__":
    print(structure_brief(300))
