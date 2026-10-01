"""pytest 全局配置与安全网（Phase 0）

铁律：
  · 默认**永不**执行 live / paid 测试，必须显式设置环境变量才放行；
  · 所有单测跑在临时 state 目录上，绝不污染真实 state/pipeline.db；
  · 提供 fake provider，任何自动测试都不允许真正提交 AutoDL 付费任务。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LIVE_ENV = "AYHMJ_RUN_LIVE"
PAID_ENV = "AYHMJ_RUN_PAID"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def pytest_configure(config: pytest.Config) -> None:
    # paid 测试必须在显式开启 paid 的前提下才允许；live 同理。
    config.addinivalue_line("markers", "unit: fast pure-logic tests")
    config.addinivalue_line("markers", "contract: third-party fixtures")
    config.addinivalue_line("markers", "integration: fake-provider flows")
    config.addinivalue_line("markers", "frontend: Playwright smoke")
    config.addinivalue_line("markers", "live: opt-in, needs network")
    config.addinivalue_line("markers", "paid: opt-in, spends real money")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    allow_live = _truthy(LIVE_ENV)
    allow_paid = _truthy(PAID_ENV)
    skip_live = pytest.mark.skip(reason=f"live test: set {LIVE_ENV}=1 to enable")
    skip_paid = pytest.mark.skip(reason=f"paid test: set {PAID_ENV}=1 to enable")
    for item in items:
        if "paid" in item.keywords and not allow_paid:
            item.add_marker(skip_paid)
        if "live" in item.keywords and not allow_live:
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture()
def tmp_state(tmp_path, monkeypatch) -> Path:
    """把 lib.state / lib.ideas / lib.genres / lib.angles / lib.products 的落盘位置
    重定向到临时目录，测试之间互不影响。"""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)

    from lib import state as state_mod
    monkeypatch.setattr(state_mod, "DB_PATH", state / "pipeline.db", raising=False)
    state_mod.init_db()

    import lib.ideas as ideas
    monkeypatch.setattr(ideas, "IDEAS_STATE", state / "used_ideas.json", raising=False)

    import lib.genres as genres
    monkeypatch.setattr(genres, "STATE", state / "genres_used.json", raising=False)

    import lib.angles as angles
    monkeypatch.setattr(angles, "STATE", state / "story_angles_used.json", raising=False)

    import lib.products as products
    monkeypatch.setattr(products, "STATE", state / "sales_points_used.json", raising=False)

    # Phase 5：Planner 也会写角色组使用记录，测试必须同样隔离
    import lib.creative.cast_groups as cast_groups
    monkeypatch.setattr(cast_groups, "GROUPS_STATE", state / "groups_used.json", raising=False)

    # Planner 现在恢复“先写完整文案再编译”的 9/26 合同。单元/集成测试必须 0 联网，
    # 所以在临时 state fixture 里给 StoryWriter 一个结构感知的假 JSON 回复。
    import re

    import lib.creative.writer as writer_mod

    def fake_story_chat(messages, **_kwargs):
        system = str(messages[0].get("content") or "")
        m_lines = re.search(r"共 (\d+) 句", system)
        m_shots = re.search(r"镜头数：(\d+)", system)
        n = int(m_lines.group(1)) if m_lines else 4
        shots = int(m_shots.group(1)) if m_shots else 4
        width = 11 if n == 6 else (12 if n <= 4 else (10 if n <= 5 else 8))
        seeds = list("甲乙丙丁戊己庚辛壬癸")
        lines = [seeds[i % len(seeds)] * width for i in range(n)]
        if n == 8:
            # 65 个纯汉字、每句唯一，避免静态门禁 R4“重复台词”。
            lines = ["爸今天就想自己走走", "我就在旁边陪着您", "累了咱就坐车歇会", "这车轻巧出门方便",
                     "前面有坡慢点走吧", "松手就停不用慌张", "到家我自己收起来", "今天这趟走得踏实"]
        return {"title": "测试短片", "goal": "测试自然故事目标", "payoff": "测试自然落点",
                "ending": "测试自然收尾", "cta": "轻轻收尾",
                "lines": lines, "shot_notes": [f"shot {i+1}" for i in range(shots)]}

    monkeypatch.setattr(writer_mod, "chat_json", fake_story_chat)
    return state


@pytest.fixture()
def fake_providers(monkeypatch):
    """把生成/LLM 供应商替换成 fake，保证测试 0 付费 0 联网。"""
    from tests.fakes.providers import FakeEnv
    env = FakeEnv()
    env.install(monkeypatch)
    return env
