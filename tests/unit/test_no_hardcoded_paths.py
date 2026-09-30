"""去硬编码回归（Phase 1）。

业务代码里不得再出现"只有当前电脑才存在"的绝对路径：
  · `D:/@kaifa/...` / `D:\\@kaifa\\...`（仓库位置必须自解析）
  · `C:/Users/<用户名>/...`（桌面/缓存目录必须走 settings）
  · 已知的外部素材库盘符路径

允许的例外：系统目录 C:/Windows/Fonts（由 lib.tools.font_dir() 统一兜底）、
config/default.yaml 里明确标注的 legacy keyfile 兼容路径（可选、缺失即跳过）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = ["lib", "tools", "s1_trend", "s2_copy", "s3_storyboard",
             "s4_generate", "s5_compose", "s6_publish", "webui", "scripts"]
SCAN_SUFFIXES = {".py", ".js"}

FORBIDDEN = [
    re.compile(r"[Dd]:[\\/]@kaifa"),
    re.compile(r"[Cc]:[\\/]Users[\\/][A-Za-z0-9_]"),
    re.compile(r"[Dd]:[\\/]BaiduSyncdisk"),
    re.compile(r"[Dd]:[\\/]自动剪辑"),
]


def _iter_sources():
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if f.suffix in SCAN_SUFFIXES and f.is_file():
                if "_deprecated" in f.parts or "vendor" in f.parts:
                    continue
                yield f


def test_no_machine_specific_paths_in_business_code():
    offenders: list[str] = []
    for path in _iter_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in FORBIDDEN:
                if pat.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "发现硬编码本机路径：\n" + "\n".join(offenders)


def test_frontend_cwd_is_injected_not_hardcoded():
    """WebUI 的 Hermes 会话 cwd 必须由服务端注入（window.__AYHMJ_ROOT__）。"""
    app_js = (ROOT / "webui" / "static" / "app.js").read_text(encoding="utf-8")
    assert "window.__AYHMJ_ROOT__" in app_js
    assert not re.search(r"cwd:\s*['\"][A-Za-z]:[\\/]", app_js)


def test_settings_has_no_hardcoded_repo_path():
    src = (ROOT / "lib" / "settings.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parent.parent" in src
    for pat in FORBIDDEN:
        assert not pat.search(src), f"lib/settings.py 不应出现硬编码路径: {pat.pattern}"
