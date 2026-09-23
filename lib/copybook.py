"""短剧结构库 — 爆款文案结构智能调用

每次文案生成（adapt_lines/脚本）自动注入结构要点：
  时间节拍 / 爽点类型 / 台词规则 / 检查清单
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRUCT_DIR = ROOT / "assets" / "scripts"


def structure_brief(max_chars: int = 2200) -> str:
    """短剧结构知识库摘要（供 LLM 文案生成智能调用）"""
    p = STRUCT_DIR / "drama_structures.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    # 去掉文档头部说明（来源行）
    lines = [ln for ln in text.splitlines() if not ln.startswith(">")]
    return "\n".join(lines)[:max_chars]


if __name__ == "__main__":
    print(structure_brief(500))
