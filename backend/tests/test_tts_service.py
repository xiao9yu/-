# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""TTS 服务测试：分句/缓存/重试降级（全部 mock，不真实联网）。"""
import pytest

from app.services import tts_service
from app.services.tts_service import TTSUnavailableError


@pytest.fixture(autouse=True)
def clear_cache():
    tts_service._cache.clear()
    yield
    tts_service._cache.clear()


def test_split_sentences_basic():
    assert tts_service.split_sentences("你好。欢迎！再见？") == ["你好。", "欢迎！", "再见？"]


def test_split_sentences_long_splits_by_comma():
    long_text = "学习率" + "很" * 130 + "，继续"
    parts = tts_service.split_sentences(long_text)
    assert len(parts) == 2
    assert len(parts[0]) > 120


def test_split_sentences_drops_punct_only():
    assert tts_service.split_sentences("你好。。欢迎！\n") == ["你好。", "欢迎！"]


def test_synthesize_caches(monkeypatch):
    calls = []

    def fake(text, voice):
        calls.append(text)
        return b"mp3"

    monkeypatch.setattr(tts_service, "_communicate", fake)
    assert tts_service.synthesize("你好") == b"mp3"
    assert tts_service.synthesize("你好") == b"mp3"
    assert len(calls) == 1


def test_synthesize_retry_then_raise(monkeypatch):
    def boom(text, voice):
        raise RuntimeError("网络失败")

    monkeypatch.setattr(tts_service, "_communicate", boom)
    with pytest.raises(TTSUnavailableError):
        tts_service.synthesize("你好")


def test_synthesize_sentences_skips_failed(monkeypatch):
    def flaky(text, voice):
        if text == "坏句。":
            raise RuntimeError("网络失败")
        return ("mp3-" + text).encode("utf-8")

    monkeypatch.setattr(tts_service, "_communicate", flaky)
    out = list(tts_service.synthesize_sentences("好句。坏句。也好。"))
    assert [s for s, _ in out] == ["好句。", "也好。"]
