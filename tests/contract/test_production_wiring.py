"""Phase 13 契约测试 —— 生产客户端真的在解析路径上装了闸门。

fixture 只能证明"契约表写对了"，证明不了"生产代码用没用它"。这里把第三方
响应换成坏 payload，断言四个调用点**当场**抛 ContractError，而不是把
KeyError / 静默错值带到下游（那正是 Phase 13 之前的老行为）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.contracts import ContractError

pytestmark = pytest.mark.contract

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"


class _Resp:
    """最小 httpx.Response 替身（只实现被生产代码用到的四个成员）。"""

    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Client:
    """最小 httpx.Client 替身（llm.chat 用 with 包住）。"""

    def __init__(self, resp) -> None:
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return self._resp


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── DeepSeek chat ──────────────────────────────────────────────────────

def test_llm_chat_passes_a_conforming_response(monkeypatch):
    import lib.llm as llm

    monkeypatch.setattr(llm, "DEEPSEEK_API_KEY", "test-key", raising=False)
    ok = _fixture("ok/deepseek_chat.chat_completion.json")
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: _Client(_Resp(ok)))
    assert json.loads(llm.chat([{"role": "user", "content": "hi"}]))["title"]


def test_llm_chat_raises_when_content_disappears(monkeypatch):
    import lib.llm as llm

    monkeypatch.setattr(llm, "DEEPSEEK_API_KEY", "test-key", raising=False)
    broken = _fixture("broken/deepseek_chat.message_without_content.json")
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: _Client(_Resp(broken)))
    with pytest.raises(ContractError) as exc:
        llm.chat([{"role": "user", "content": "hi"}])
    assert "choices[].message.content" in str(exc.value)


def test_llm_chat_raises_when_choices_is_not_a_list(monkeypatch):
    import lib.llm as llm

    monkeypatch.setattr(llm, "DEEPSEEK_API_KEY", "test-key", raising=False)
    broken = _fixture("broken/deepseek_chat.choices_not_list.json")
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: _Client(_Resp(broken)))
    with pytest.raises(ContractError):
        llm.chat([{"role": "user", "content": "hi"}])


# ── AutoDL 提交 / 查询 ─────────────────────────────────────────────────

def test_autodl_create_task_accepts_a_conforming_response(monkeypatch):
    import s4_generate.autodl_client as ac

    monkeypatch.setattr(ac, "API_KEY", "test-key", raising=False)
    ok = _fixture("ok/autodl_submit.queued.json")
    monkeypatch.setattr(ac.httpx, "post", lambda *a, **k: _Resp(ok))
    assert ac.create_task("wf", {"prompt": "x"}) == ok["data"]["task_id"]


def test_autodl_create_task_raises_on_blank_task_id(monkeypatch):
    import s4_generate.autodl_client as ac

    monkeypatch.setattr(ac, "API_KEY", "test-key", raising=False)
    broken = _fixture("broken/autodl_submit.empty_task_id.json")
    monkeypatch.setattr(ac.httpx, "post", lambda *a, **k: _Resp(broken))
    with pytest.raises(ContractError):
        ac.create_task("wf", {"prompt": "x"})


def test_autodl_query_task_accepts_a_running_task(monkeypatch):
    import s4_generate.autodl_client as ac

    monkeypatch.setattr(ac, "API_KEY", "test-key", raising=False)
    ok = _fixture("ok/autodl_result.running.json")
    monkeypatch.setattr(ac.httpx, "get", lambda *a, **k: _Resp(ok))
    assert ac.query_task("task_1")["status"] == "RUNNING"


def test_autodl_query_task_raises_when_results_shape_drifts(monkeypatch):
    import s4_generate.autodl_client as ac

    monkeypatch.setattr(ac, "API_KEY", "test-key", raising=False)
    broken = _fixture("broken/autodl_result.results_not_list.json")
    monkeypatch.setattr(ac.httpx, "get", lambda *a, **k: _Resp(broken))
    with pytest.raises(ContractError):
        ac.query_task("task_1")


def test_autodl_query_task_raises_when_success_has_no_url(monkeypatch):
    import s4_generate.autodl_client as ac

    monkeypatch.setattr(ac, "API_KEY", "test-key", raising=False)
    broken = _fixture("broken/autodl_result.success_without_url.json")
    monkeypatch.setattr(ac.httpx, "get", lambda *a, **k: _Resp(broken))
    with pytest.raises(ContractError) as exc:
        ac.query_task("task_1")
    assert "data.results[].url" in str(exc.value)


# ── Upload-Post 上传 / 状态 / 账号 ─────────────────────────────────────

@pytest.fixture()
def _uploadpost(monkeypatch):
    """隔离凭据与 profile，避免测试真的去读 keyring / pipeline.yaml。"""
    import s6_publish.uploadpost as up

    monkeypatch.setattr(up, "api_key", lambda: "test-key", raising=False)
    monkeypatch.setattr(up, "default_profile", lambda: "test-profile", raising=False)
    return up


def test_uploadpost_upload_accepts_a_queued_response(_uploadpost, monkeypatch, tmp_path):
    up = _uploadpost
    ok = _fixture("ok/uploadpost_upload.queued.json")
    monkeypatch.setattr(up.httpx, "post", lambda *a, **k: _Resp(ok))
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    assert up.upload_video(str(video), "标题", ["tiktok"])["request_id"] == ok["request_id"]


def test_uploadpost_upload_raises_without_request_id(_uploadpost, monkeypatch, tmp_path):
    up = _uploadpost
    broken = _fixture("broken/uploadpost_upload.no_request_id.json")
    monkeypatch.setattr(up.httpx, "post", lambda *a, **k: _Resp(broken))
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(ContractError):
        up.upload_video(str(video), "标题", ["tiktok"])


def test_uploadpost_status_accepts_a_completed_response(_uploadpost, monkeypatch):
    up = _uploadpost
    ok = _fixture("ok/uploadpost_status.completed.json")
    monkeypatch.setattr(up.httpx, "get", lambda *a, **k: _Resp(ok))
    body = up.upload_status("req_1")
    assert body["results"]["tiktok"]["status"] == "completed"


def test_uploadpost_status_rejects_a_non_object_body(_uploadpost, monkeypatch):
    up = _uploadpost
    broken = _fixture("broken/uploadpost_status.not_object.json")
    monkeypatch.setattr(up.httpx, "get", lambda *a, **k: _Resp(broken))
    with pytest.raises(ContractError):
        up.upload_status("req_1")


def test_uploadpost_status_rejects_a_platform_value_that_is_not_an_object(_uploadpost, monkeypatch):
    up = _uploadpost
    broken = _fixture("broken/uploadpost_status.item_not_object.json")
    monkeypatch.setattr(up.httpx, "get", lambda *a, **k: _Resp(broken))
    with pytest.raises(ContractError):
        up.upload_status("req_1")


def test_uploadpost_whoami_raises_on_wrong_field_type(_uploadpost, monkeypatch):
    up = _uploadpost
    broken = _fixture("broken/uploadpost_me.bad_field_type.json")
    monkeypatch.setattr(up.httpx, "get", lambda *a, **k: _Resp(broken))
    with pytest.raises(ContractError):
        up.whoami()


def test_uploadpost_whoami_accepts_a_profile_response(_uploadpost, monkeypatch):
    up = _uploadpost
    ok = _fixture("ok/uploadpost_me.profile.json")
    monkeypatch.setattr(up.httpx, "get", lambda *a, **k: _Resp(ok))
    assert up.whoami()["profile"] == "ayh-main"
