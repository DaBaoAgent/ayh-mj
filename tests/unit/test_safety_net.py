"""安全网自证：自动测试阶段 0 付费、0 真实提交（Phase 0）。"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit


def test_paid_and_live_markers_are_gated():
    """默认没有 AYHMJ_RUN_PAID / AYHMJ_RUN_LIVE 时，任何标记测试都不该被视为放行。"""
    if os.environ.get("AYHMJ_RUN_PAID", "").strip() in {"1", "true", "yes", "on"}:
        pytest.skip("paid 显式开启，跳过门禁自证")
    assert os.environ.get("AYHMJ_RUN_PAID", "") == ""
    assert os.environ.get("AYHMJ_RUN_LIVE", "") == ""


def test_fake_provider_counts_and_blocks_real_calls(fake_providers):
    """fake 装上后，调用只累加计数，绝不发网络请求。"""
    import s4_generate.autodl_client as ac
    task_id = ac.create_task("minimax_h3_lightx2v_v5", {"prompt": "x"})
    assert task_id == "fake_task_1"
    assert fake_providers.log.create_task == 1
    assert fake_providers.log.query_task == 0


def test_fake_provider_can_simulate_workflow_failure(fake_providers):
    import s4_generate.autodl_client as ac
    fake_providers.fail_workflows.add("bad_wf")
    with pytest.raises(RuntimeError):
        ac.create_task("bad_wf", {})
    assert fake_providers.log.create_task == 1


def test_fake_download_can_fail_then_succeed(fake_providers, tmp_path):
    import s4_generate.autodl_client as ac
    fake_providers.download_fail_times = 1
    with pytest.raises(RuntimeError):
        ac.download("fake://x.mp4", str(tmp_path / "a.mp4"))
    out = ac.download("fake://x.mp4", str(tmp_path / "a.mp4"))
    assert fake_providers.log.download == 2
    assert (tmp_path / "a.mp4").exists()
    assert out.endswith("a.mp4")
