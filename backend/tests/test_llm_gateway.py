# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import json

import httpx
import pytest

from app.services.llm_gateway import LLMError, LLMGateway

CHAT_JSON = {
    "id": "1", "object": "chat.completion", "created": 1, "model": "deepseek-chat",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "你好"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _gw(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMGateway(api_key="sk-test", base_url="https://api.test", backoff_base=0.01, http_client=client)


def test_chat_returns_content():
    def handler(request):
        return httpx.Response(200, json=CHAT_JSON)

    assert _gw(handler).chat([{"role": "user", "content": "hi"}]) == "你好"


def test_chat_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": {"message": "busy"}}, headers={"retry-after": "0"})
        return httpx.Response(200, json=CHAT_JSON)

    assert _gw(handler).chat([{"role": "user", "content": "hi"}]) == "你好"
    assert calls["n"] == 3


def test_chat_raises_after_max_retries():
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "busy"}}, headers={"retry-after": "0"})

    with pytest.raises(LLMError):
        _gw(handler).chat([{"role": "user", "content": "hi"}])


def test_chat_json_repairs_bad_json():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        body = json.loads(request.content)
        if calls["n"] == 1:
            resp = dict(CHAT_JSON, choices=[{"index": 0, "message": {"role": "assistant", "content": "not-json"}, "finish_reason": "stop"}])
        else:
            resp = dict(CHAT_JSON, choices=[{"index": 0, "message": {"role": "assistant", "content": '{"ok": true}'}, "finish_reason": "stop"}])
        return httpx.Response(200, json=resp)

    assert _gw(handler).chat_json([{"role": "user", "content": "输出 JSON"}]) == {"ok": True}
    assert calls["n"] == 2


def test_chat_json_requires_json_keyword_in_prompt():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        resp = dict(CHAT_JSON, choices=[{"index": 0, "message": {"role": "assistant", "content": '{"a": 1}'}, "finish_reason": "stop"}])
        return httpx.Response(200, json=resp)

    _gw(handler).chat_json([{"role": "user", "content": "给我结果"}])
    assert "JSON" in seen["body"]["messages"][-1]["content"]


def test_chat_stream_yields_deltas():
    from unittest.mock import patch

    gw = LLMGateway(api_key="sk-test", base_url="https://api.test", backoff_base=0.01)

    class Delta:
        def __init__(self, content): self.content = content

    class Choice:
        def __init__(self, content): self.delta = Delta(content)

    class Chunk:
        def __init__(self, content): self.choices = [Choice(content)]

    class FakeStream:
        def __iter__(self):
            return iter([Chunk("你"), Chunk("好")])

    with patch.object(gw.client.chat.completions, "create", return_value=FakeStream()):
        assert list(gw.chat_stream([{"role": "user", "content": "hi"}])) == ["你", "好"]


def test_chat_without_api_key_raises():
    gw = LLMGateway(api_key="", base_url="https://api.test")
    with pytest.raises(LLMError, match="DEEPSEEK_API_KEY"):
        gw.chat([{"role": "user", "content": "hi"}])


def test_nonretryable_error_wrapped_as_llmerror(monkeypatch):
    """非可重试 SDK 错误（错 key 401 等）应包成 LLMError 且不重试（台账 A-2）。"""
    from app.services.llm_gateway import LLMError, LLMGateway

    calls = []
    def boom(**kwargs):
        calls.append(1)
        raise RuntimeError("401 Unauthorized")
    gw = LLMGateway(api_key="sk-test")
    monkeypatch.setattr(gw.client.chat.completions, "create", boom)
    import pytest
    with pytest.raises(LLMError, match="大模型调用失败"):
        gw.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1
