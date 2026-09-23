"""产品卖点库 — 从归档的卖点文档提供文案素材"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POINTS_DIR = ROOT / "assets" / "products"


def sales_points_brief(max_chars: int = 900) -> str:
    """读卖点库 → 摘要（供 LLM 文案/提示词引用真实卖点参数）"""
    p = POINTS_DIR / "轻便侠218_卖点.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    # 截取正文（跳标题行）
    return text[:max_chars]


if __name__ == "__main__":
    print(sales_points_brief(400))
