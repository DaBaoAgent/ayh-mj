"""统一密钥解析回归（Phase 1）。

优先级：环境变量 → keyring → dotenv → 兼容 keyfile。
关键约束：找不到密钥返回空串（由 health 层报 DEGRADED），绝不 import 即崩，
也不依赖任何"本机才存在"的固定文件路径。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import secrets

pytestmark = pytest.mark.unit

ENV_VARS = ("AUTODL_API_KEY", "DEEPSEEK_API_KEY", "VOLCANO_API_KEY", "UPLOADPOST_API_KEY")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """隔离真实环境：清环境变量、禁 keyring、禁用默认文件源。"""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(secrets, "_from_keyring", lambda name: "")
    monkeypatch.setattr(secrets, "dotenv_files", list)
    monkeypatch.setattr(secrets, "labelled_keyfiles", list)
    yield


def test_missing_secret_returns_empty_not_crash():
    assert secrets.get_secret("deepseek") == ""
    assert secrets.has_secret("deepseek") is False
    assert secrets.secret_source("deepseek") == "missing"


def test_env_var_has_highest_priority(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert secrets.get_secret("deepseek") == "env-key"
    assert secrets.secret_source("deepseek") == "env:DEEPSEEK_API_KEY"


def test_env_beats_keyring(monkeypatch):
    monkeypatch.setenv("AUTODL_API_KEY", "env-wins")
    monkeypatch.setattr(secrets, "_from_keyring", lambda name: "keyring-loses")
    assert secrets.get_secret("autodl") == "env-wins"


def test_keyring_used_when_no_env(monkeypatch):
    monkeypatch.setattr(secrets, "_from_keyring", lambda name: "kr-key" if name == "autodl" else "")
    assert secrets.get_secret("autodl") == "kr-key"
    assert secrets.secret_source("autodl") == "keyring"


def test_dotenv_parsed_before_keyfile(monkeypatch, tmp_path):
    env_file = tmp_path / "ark.env"
    env_file.write_text('DEEPSEEK_API_KEY="dotenv-key"\n# comment\n', encoding="utf-8")
    monkeypatch.setattr(secrets, "dotenv_files", lambda: [env_file])
    assert secrets.get_secret("deepseek") == "dotenv-key"
    assert secrets.secret_source("deepseek") == "dotenv"


def test_legacy_keyfile_is_last_resort(monkeypatch, tmp_path):
    key_file = tmp_path / "api_keys.txt"
    key_file.write_text("deepseek：\nlegacy-key\n", encoding="utf-8")
    monkeypatch.setattr(secrets, "labelled_keyfiles", lambda: [key_file])
    assert secrets.get_secret("deepseek") == "legacy-key"
    assert secrets.secret_source("deepseek") == "keyfile(legacy)"


def test_allow_files_false_never_touches_disk(monkeypatch, tmp_path):
    key_file = tmp_path / "api_keys.txt"
    key_file.write_text("deepseek：\nlegacy-key\n", encoding="utf-8")
    monkeypatch.setattr(secrets, "labelled_keyfiles", lambda: [key_file])
    assert secrets.get_secret("deepseek", allow_files=False) == ""


def test_missing_files_are_silently_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(secrets, "labelled_keyfiles", lambda: [tmp_path / "nope.txt"])
    monkeypatch.setattr(secrets, "dotenv_files", lambda: [tmp_path / "none.env"])
    assert secrets.get_secret("volcano") == ""


def test_keyfile_parser_reads_label_then_value(tmp_path):
    from lib.keyfile import load_from_keyfile

    f = Path(tmp_path) / "keys.txt"
    f.write_text("autodl api：\nkey-autodl\n火山方舟：\nkey-volcano\n", encoding="utf-8")
    assert load_from_keyfile("autodl", path=f) == "key-autodl"
    assert load_from_keyfile("火山", path=f) == "key-volcano"
    assert load_from_keyfile("不存在", path=f) == ""
