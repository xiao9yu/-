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


# ---------- 流式三段超时保护（评测 §5.5） ----------

def _fake_chunks(contents):
    class Delta:
        def __init__(self, content): self.content = content

    class Choice:
        def __init__(self, content): self.delta = Delta(content)

    class Chunk:
        def __init__(self, content): self.choices = [Choice(content)]

    return [Chunk(c) for c in contents]


class _TimedStream:
    """按预设间隔推进假时钟后再吐出下一块，模拟块间真实等待。"""

    def __init__(self, chunks, gaps, clock):
        self.chunks = chunks
        self.gaps = gaps
        self.clock = clock

    def __iter__(self):
        for chunk, gap in zip(self.chunks, self.gaps):
            self.clock["t"] += gap
            yield chunk


def _stream_gw(monkeypatch, chunks, gaps):
    import app.services.llm_gateway as lg

    gw = LLMGateway(api_key="sk-test", base_url="https://api.test")
    clock = {"t": 0.0}
    monkeypatch.setattr(lg.time, "monotonic", lambda: clock["t"])
    stream = _TimedStream(chunks, gaps, clock)
    monkeypatch.setattr(gw.client.chat.completions, "create", lambda **kw: stream)
    return gw


def test_chat_stream_first_token_timeout_raises(monkeypatch):
    """首个内容块超过首字阈值才到达 → LLMError 指明首字超时。"""
    gw = _stream_gw(monkeypatch, _fake_chunks(["你", "好"]), gaps=[31, 1])
    with pytest.raises(LLMError, match="首字超时"):
        list(gw.chat_stream([{"role": "user", "content": "hi"}], first_token_timeout=30.0))


def test_chat_stream_overall_timeout_stops_stream(monkeypatch):
    """总时长越限 → 已吐出的块保留、随后报整体超时。"""
    gw = _stream_gw(monkeypatch, _fake_chunks(["a", "b", "c", "d"]), gaps=[10, 10, 10, 10])
    pieces = []
    with pytest.raises(LLMError, match="整体超时"):
        for p in gw.chat_stream([{"role": "user", "content": "hi"}], overall_timeout=30.0):
            pieces.append(p)
    assert pieces == ["a", "b", "c"]


def test_chat_stream_silence_timeout_raises(monkeypatch):
    """两内容块间隔超过静默阈值 → LLMError 指明静默超时。"""
    gw = _stream_gw(monkeypatch, _fake_chunks(["a", "b"]), gaps=[5, 30])
    with pytest.raises(LLMError, match="静默超时"):
        list(gw.chat_stream([{"role": "user", "content": "hi"}], silence_timeout=20.0))


def test_chat_stream_within_limits_yields_all(monkeypatch):
    """各段耗时都在阈值内 → 全部正常吐出。"""
    gw = _stream_gw(monkeypatch, _fake_chunks(["你", "好", "呀"]), gaps=[1, 1, 1])
    out = list(gw.chat_stream([{"role": "user", "content": "hi"}],
                              first_token_timeout=10.0, overall_timeout=10.0, silence_timeout=5.0))
    assert out == ["你", "好", "呀"]


def test_chat_stream_sets_sdk_read_timeout_from_silence(monkeypatch):
    """静默阈值同步收紧 SDK 读超时：卡死的连接不必等 60s 默认值。"""
    gw = LLMGateway(api_key="sk-test", base_url="https://api.test")
    captured = {}

    def create(**kw):
        captured.update(kw)
        return _TimedStream([], [], {"t": 0.0})

    monkeypatch.setattr(gw.client.chat.completions, "create", create)
    list(gw.chat_stream([{"role": "user", "content": "hi"}], silence_timeout=7.0))
    assert captured["timeout"].read == 7.0


def test_chat_stream_sdk_read_timeout_wrapped_as_llmerror(monkeypatch):
    """SDK 读超时（连接静默卡死）→ 包成 LLMError 且信息指明超时。"""
    from openai import APITimeoutError

    class FakeTimeout(APITimeoutError):
        def __init__(self): pass

    class TimeoutStream:
        def __iter__(self):
            yield _fake_chunks(["部分"])[0]
            raise FakeTimeout()

    gw = LLMGateway(api_key="sk-test", base_url="https://api.test")
    monkeypatch.setattr(gw.client.chat.completions, "create", lambda **kw: TimeoutStream())
    with pytest.raises(LLMError, match="超时"):
        list(gw.chat_stream([{"role": "user", "content": "hi"}]))
