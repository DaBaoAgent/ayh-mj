"""paid 测试示例：默认永不执行，只有 AYHMJ_RUN_PAID=1 才放行。

用 `pytest -m paid` 显式选择，并设置 AYHMJ_RUN_PAID=1 才可能真正跑到这里。
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.paid, pytest.mark.live]


def test_paid_placeholder_requires_explicit_optin():
    assert os.environ.get("AYHMJ_RUN_PAID") == "1", "paid 测试必须在显式开启时才可能运行"
