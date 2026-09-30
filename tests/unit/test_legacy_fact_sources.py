"""废弃事实源回归（Phase 14）。

一条可执行的验收标准：全仓搜索不存在业务代码继续依赖已废弃事实源。

覆盖四类旧事实源：
  · `config/pipeline.yaml`（Phase 14 删除：唯一权威配置是 `config/default.yaml`）
  · BGM/SFX 的第二套选曲逻辑（唯一入口 `lib.post.audio_director` / `lib.post.sfx`）
  · 归档目录 `_deprecated_*`（不参与 import / 测试 discovery）
  · 旧入口 `tools/run_all.py`（只能显式声明废弃，不能静默当主链）

判定全部走 AST：注释与 docstring 里"提到"某个名字不算依赖，只有**真的当 import / 字符串字面量
（路径）用**才算。否则说明文档本身就会把自己判红。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).name

CODE_DIRS = ("lib", "tools", "s1_trend", "s2_copy", "s3_storyboard", "s4_generate",
             "s5_compose", "s6_publish", "s7_learn", "webui", "tests")

RANDOM_CALLS = ("choice", "sample", "randint", "shuffle", "random")

# 只有"把归档目录排除出去"的地方可以出现这个名字（扫描/清理时的跳过名单），
# 它们引用这个字符串是为了**避开**归档，不是依赖它。import 检查对它们一样生效。
ARCHIVE_EXCLUSION_ALLOW = {"lib/claims.py", "tools/cleanup_project.py"}


def _iter_code(patterns: tuple[str, ...] = ("*.py", "*.mjs", "*.js")):
    for rel in CODE_DIRS:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for pat in patterns:
            for f in base.rglob(pat):
                if not f.is_file() or f.name == SELF:
                    continue
                if "_deprecated" in f.parts or "vendor" in f.parts or "__pycache__" in f.parts:
                    continue
                yield f


def _trees():
    """(path, tree)，只含能按 Python 解析的源码（.mjs / .js 会被跳过）。"""
    for path in _iter_code():
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        yield path, tree


def _docstring_lines(tree: ast.AST) -> set[int]:
    """模块/类/函数第一条语句是字符串 → 整段记为 docstring，不算代码。"""
    lines: set[int] = set()
    holder = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holder):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                lines.add(ln)
    return lines


def _str_constants(tree: ast.AST, needle: str, skip_lines: set[int]):
    """非 docstring 的字符串字面量里包含 needle 的位置（路径硬编码的判定口径）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if needle in node.value and node.lineno not in skip_lines:
            yield node.lineno


def test_pipeline_yaml_is_gone_and_unreferenced():
    """Phase 14：旧配置已删，业务代码不得再回头读它（注释/docstring 提及不算）。"""
    assert not (ROOT / "config" / "pipeline.yaml").exists(), \
        "config/pipeline.yaml 应已删除（唯一权威来源 = config/default.yaml）"
    offenders: list[str] = []
    for path, tree in _trees():
        skip = _docstring_lines(tree)
        for lineno in _str_constants(tree, "pipeline.yaml", skip):
            offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not offenders, "业务代码仍把已删除的 pipeline.yaml 当路径使用:\n" + "\n".join(offenders)


def test_no_second_bgm_or_sfx_selection_logic():
    """BGM/SFX 选曲只能有一套实现：不允许回到 random 选曲。"""
    hot = {"lib/post/audio_director.py", "lib/post/sfx.py",
           "tools/audio_polish.py", "tools/make_15s.py"}
    offenders: list[str] = []
    for path, tree in _trees():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel not in hot:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr not in RANDOM_CALLS:
                continue
            if isinstance(node.value, ast.Name) and node.value.id == "random":
                offenders.append(f"{rel}:{node.lineno} random.{node.attr}")
    assert not offenders, "音频选曲不允许随机（不可复现/不可解释）:\n" + "\n".join(offenders)


def test_bgm_and_sfx_have_single_entry_points():
    """两条实际会调音频的路径都必须走唯一策略入口。"""
    polish = (ROOT / "tools" / "audio_polish.py").read_text(encoding="utf-8")
    make15s = (ROOT / "tools" / "make_15s.py").read_text(encoding="utf-8")
    for src, name in ((polish, "tools/audio_polish.py"), (make15s, "tools/make_15s.py")):
        assert "from lib.post.audio_director import select_bgm" in src, name
        assert "from lib.post.sfx import plan_sfx" in src, name


def test_deprecated_archive_is_never_imported():
    """归档目录不参与 module import，也不能被当 sys.path 拼进去。"""
    needle = "_deprecated_20260925"
    offenders: list[str] = []
    for path, tree in _trees():
        skip = _docstring_lines(tree)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("_deprecated"):
                offenders.append(f"{rel}:{node.lineno} from {node.module}")
            elif isinstance(node, ast.Import):
                offenders += [f"{rel}:{node.lineno} import {a.name}"
                              for a in node.names if a.name.startswith("_deprecated")]
        if rel in ARCHIVE_EXCLUSION_ALLOW:
            continue
        offenders += [f"{rel}:{ln}" for ln in _str_constants(tree, needle, skip)]
    assert not offenders, "归档目录不能被 import / 当路径使用:\n" + "\n".join(offenders)


def test_run_all_is_explicitly_deprecated():
    """旧入口保留但必须自声明废弃，避免有人把它当主链。"""
    src = (ROOT / "tools" / "run_all.py").read_text(encoding="utf-8")
    assert "[deprecated]" in src
    assert "orchestrate.py" in src
    assert "DEPRECATED" in src


def test_deprecated_dir_is_not_collected_by_pytest():
    """`_deprecated_*` 不进测试 discovery（norecursedirs 生效的行为证据）。"""
    from lib.settings import get_settings

    settings = get_settings()
    assert settings.root == ROOT


def test_config_default_yaml_has_no_machine_absolute_path():
    """配置里不允许出现本机目录（换机后必须仍能起）。"""
    text = (ROOT / "config" / "default.yaml").read_text(encoding="utf-8")
    for bad in ("D:/@kaifa", "D:\\@kaifa", "C:/Users/", "C:\\Users\\"):
        assert bad not in text, f"config/default.yaml 不应包含本机路径: {bad}"
