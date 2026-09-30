"""ideas.novelty_issue —— 花大钱前就要拦掉复读台词（Phase 0）。"""
from __future__ import annotations

import pytest

import lib.ideas as ideas

pytestmark = pytest.mark.unit


def test_novelty_issue_empty_when_no_history(tmp_state):
    assert ideas.novelty_issue({"1": "全新的开场白", "2": "完全没写过"}) == ""


def test_novelty_issue_flags_identical_template_lines(tmp_state):
    lines = {"1": "十三点八公斤", "2": "单手就能提"}
    assert ideas.novelty_issue(lines, standard_lines=dict(lines)) == "台词与模板标准版完全相同"


def test_novelty_issue_flags_near_duplicate_script(tmp_state):
    ideas.record_idea("T01", "换车", "热点", {"1": "这车真轻便", "2": "单手就能提起来"})
    issue = ideas.novelty_issue({"1": "这车真轻便", "2": "单手就能提起来"})
    assert "过于相似" in issue


def test_novelty_issue_flags_recycled_hook(tmp_state):
    ideas.record_idea("T01", "换车", "热点", {"1": "邻居家老王又换新车了", "2": "关我什么事呢"})
    issue = ideas.novelty_issue({"1": "邻居家老王又换新车了", "2": "今天天气真的不错啊"})
    assert "开场钩子" in issue


def test_novelty_issue_allows_genuinely_new(tmp_state):
    ideas.record_idea("T01", "换车", "热点", {"1": "邻居家老王又换新车了", "2": "关我什么事呢"})
    issue = ideas.novelty_issue({"1": "菜市场里人来人往真热闹", "2": "老板给我来二斤西红柿"})
    assert issue == ""
