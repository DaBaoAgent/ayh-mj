"""统一配置解析回归（Phase 1）。

覆盖：权威源 default.yaml、环境变量覆盖 AYHMJ_<SEC>__<KEY>、路径自解析、
仓库换目录后仍可用（ROOT 不写死）、legacy pipeline.yaml 只兜底不夺权。
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from lib.settings import (
    DEFAULT_CONFIG,
    ROOT,
    load_settings,
    reset_settings_cache,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """清掉可能存在的 AYHMJ_* 覆盖，让每个用例从干净状态开始。"""
    import os
    for key in list(os.environ):
        if key.startswith("AYHMJ_"):
            monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_default_config_exists_and_parses():
    assert DEFAULT_CONFIG.exists(), "config/default.yaml 必须存在（唯一权威配置）"
    s = load_settings()
    assert s.product.name
    assert s.llm.provider == "deepseek"
    assert s.asr.backend == "faster-whisper"
    assert s.generate.prompt_max_chars > 0


def test_root_is_derived_from_repo_not_hardcoded():
    s = load_settings()
    assert s.root == ROOT
    assert Path(s.root) == Path(__file__).resolve().parents[2]


def test_resolve_relative_paths_under_root():
    s = load_settings()
    assert s.state_dir == s.root / "state"
    assert s.out_dir == s.root / "out"


def test_env_override_simple_and_nested(monkeypatch):
    monkeypatch.setenv("AYHMJ_LLM__MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("AYHMJ_GENERATE__DURATION", "10")
    monkeypatch.setenv("AYHMJ_PATHS__FFMPEG", "/tmp/fake-ffmpeg")
    s = load_settings()
    assert s.llm.model == "deepseek-v4-pro"
    assert s.generate.duration == 10          # 字符串被强制转成 int
    assert s.paths.ffmpeg == "/tmp/fake-ffmpeg"


def test_env_bool_coercion(monkeypatch):
    monkeypatch.setenv("AYHMJ_WEBUI__DEBUG", "true")
    assert load_settings().webui.debug is True
    monkeypatch.setenv("AYHMJ_WEBUI__DEBUG", "false")
    assert load_settings().webui.debug is False


def test_root_env_override_makes_repo_relocatable(monkeypatch, tmp_path):
    """仓库复制到别的目录：设 AYHMJ_ROOT 后所有路径跟着走，无需改源码。"""
    other = tmp_path / "copied-repo"
    other.mkdir()
    monkeypatch.setenv("AYHMJ_ROOT", str(other))
    s = load_settings()
    assert s.root == other.resolve()
    assert s.state_dir == other.resolve() / "state"


def test_explicit_config_path(tmp_path):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            llm:
              model: custom-model
            paths:
              state_dir: "var/state"
            """
        ),
        encoding="utf-8",
    )
    s = load_settings(cfg)
    assert s.llm.model == "custom-model"
    assert s.state_dir == s.root / "var" / "state"
    # 未覆盖的键回落到 pydantic 默认
    assert s.llm.provider == "deepseek"
