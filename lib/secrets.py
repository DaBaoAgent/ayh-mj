"""统一密钥解析（Phase 1）—— 全仓唯一入口，业务模块不再各自猜文件位置。

优先级（高 → 低）
  1. 环境变量（AUTODL_API_KEY / DEEPSEEK_API_KEY / VOLCANO_API_KEY / UPLOADPOST_API_KEY）
  2. 系统凭据库 keyring（service = 逻辑名，user = "api_key"）
  3. dotenv 风格文件 `KEY=VALUE`（仓库内 state/*.env + $LOCALAPPDATA/hermes/.env）
  4. 兼容：旧式"标签 + 下一行裸 key"文本文件（config/api_keys.txt 或
     settings.paths.legacy_keyfiles —— 不存在就静默跳过，绝不是运行必需条件）

设计目标：找不到密钥时返回空串，由 capability/health 层报 DEGRADED，
而不是让业务模块 import 即崩或各自去猜路径。
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from .settings import get_settings
except ImportError:  # pragma: no cover - 允许 `python lib/secrets.py` 直接运行
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lib.settings import get_settings

# 逻辑名 → 环境变量名
ENV_NAMES = {
    "autodl": "AUTODL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "火山": "VOLCANO_API_KEY",
    "volcano": "VOLCANO_API_KEY",
    "uploadpost": "UPLOADPOST_API_KEY",
}
# 逻辑名 → 旧标签文件里的标签（兼容用）
LEGACY_LABELS = {
    "autodl": ("autodl",),
    "deepseek": ("deepseek",),
    "火山": ("火山",),
    "volcano": ("火山",),
    "uploadpost": ("uploadpost", "upload-post"),
}


def _dedupe(paths: list[Path]) -> list[Path]:
    seen, out = set(), []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def labelled_keyfiles() -> list[Path]:
    """旧式标签格式的候选文件（按优先级）。"""
    s = get_settings()
    out: list[Path] = []
    env_path = os.environ.get("AYHMJ_KEYFILE") or s.paths.keyfile
    if env_path:
        out.append(Path(env_path).expanduser())
    out.append(s.root / "config" / "api_keys.txt")
    out.extend(s.resolve(p) for p in s.paths.legacy_keyfiles)
    return _dedupe(out)


def dotenv_files() -> list[Path]:
    """dotenv 风格候选文件（按优先级）。"""
    s = get_settings()
    out = [s.resolve(p) for p in s.paths.dotenv_files]
    out.append(s.root / ".env")
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        out.append(Path(localappdata) / "hermes" / ".env")
    return _dedupe(out)


# 兼容旧名（Phase 0/1 之前有调用方按这个语义找 key 文件）
def candidate_keyfiles() -> list[Path]:
    return labelled_keyfiles()


def _from_dotenv(name: str) -> str:
    env_name = ENV_NAMES.get(name, name.upper())
    for path in dotenv_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == env_name:
                return value.strip().strip('"').strip("'")
    return ""


def _from_keyring(name: str) -> str:
    """系统凭据库读取（keyring 缺失/锁定时静默返回空串）。"""
    try:
        import keyring
        return (keyring.get_password(name, "api_key") or "").strip()
    except Exception:
        return ""


def _from_keyfile(name: str) -> str:
    try:
        from .keyfile import load_from_keyfile
    except ImportError:  # pragma: no cover - 允许 `python lib/secrets.py` 直接运行
        from lib.keyfile import load_from_keyfile
    for label in LEGACY_LABELS.get(name, (name,)):
        for path in labelled_keyfiles():
            key = load_from_keyfile(label, path=path)
            if key:
                return key
    return ""


def get_secret(name: str, *, allow_files: bool = True) -> str:
    """取密钥；找不到返回空串。"""
    env_name = ENV_NAMES.get(name, name.upper())
    value = (os.environ.get(env_name) or "").strip()
    if value:
        return value

    value = _from_keyring(name)
    if value:
        return value

    if not allow_files:
        return ""
    return _from_dotenv(name) or _from_keyfile(name)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def secret_source(name: str) -> str:
    """返回密钥来源描述（用于 health/capability 报告，不泄露值）。"""
    env_name = ENV_NAMES.get(name, name.upper())
    if (os.environ.get(env_name) or "").strip():
        return f"env:{env_name}"
    if _from_keyring(name):
        return "keyring"
    if _from_dotenv(name):
        return "dotenv"
    if _from_keyfile(name):
        return "keyfile(legacy)"
    return "missing"


if __name__ == "__main__":
    for logical in ("autodl", "deepseek", "火山", "uploadpost"):
        src = secret_source(logical)
        print(f"{logical}: {'✓ ' if src != 'missing' else '✗ '}{src}")
