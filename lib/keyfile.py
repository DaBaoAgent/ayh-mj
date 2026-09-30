"""旧式 API key 文本文件解析（兼容层，非默认必需）

格式（中文标签行 + 下一行裸 key）：
    autodl api：
    <key>
    火山方舟：
    <key>
    deepseek：
    <key>

Phase 1 起：路径不再写死机器专属目录。
  · 默认查找 `$AYHMJ_KEYFILE` / `settings.paths.keyfile` / `<root>/config/api_keys.txt`
  · `load_from_keyfile(label, path=...)` 可显式指定文件（测试与 legacy 使用）
"""
from __future__ import annotations

from pathlib import Path

# 保留常量名以兼容既有 import；取值在调用时动态解析（避免导入即依赖 settings）。
KEY_FILE: Path | None = None


def _default_paths() -> list[Path]:
    from .secrets import candidate_keyfiles
    return [p for p in candidate_keyfiles() if p.suffix != ".env"]


def load_from_keyfile(label: str, path: Path | str | None = None) -> str:
    """按标签读 key；找不到文件或标签返回空串。"""
    paths = [Path(path)] if path else ([KEY_FILE] if KEY_FILE else _default_paths())
    for candidate in paths:
        if candidate is None or not Path(candidate).exists():
            continue
        try:
            lines = [ln.strip() for ln in Path(candidate).read_text(encoding="utf-8").splitlines()]
        except (OSError, UnicodeDecodeError):
            continue
        for i, ln in enumerate(lines):
            if label in ln:
                for j in range(i + 1, len(lines)):
                    if lines[j]:
                        return lines[j]
    return ""


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lib.secrets import get_secret
    for name in ("autodl", "deepseek", "火山"):
        k = get_secret(name)
        print(f"{name}: {'✓ ' + k[:8] + '...(' + str(len(k)) + '字符)' if k else '✗ 未找到'}")
