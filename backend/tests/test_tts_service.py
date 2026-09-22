# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""TTS 服务测试：分句/缓存/重试降级（全部 mock，不真实联网）。"""
import pytest

from app.services import tts_service
from app.services.tts_service import TTSUnavailableError


@pytest.fixture(autouse=True)
def clear_cache():
    tts_service._cache.clear()
    tts_service._timed_cache.clear()
    yield
    tts_service._cache.clear()
    tts_service._timed_cache.clear()


def test_split_sentences_basic():
    assert tts_service.split_sentences("你好。欢迎！再见？") == ["你好。", "欢迎！", "再见？"]


def test_split_sentences_long_splits_by_comma():
    long_text = "学习率" + "很" * 130 + "，继续"
    parts = tts_service.split_sentences(long_text)
    assert len(parts) == 2
    assert len(parts[0]) > 120


def test_split_sentences_drops_punct_only():
    assert tts_service.split_sentences("你好。。欢迎！\n") == ["你好。", "欢迎！"]


def test_spoken_text_strips_cites_and_ref_prefix():
    # 引用编号、markdown 强调符与"参考答案："式前缀仅朗读时去除，展示文本不受影响
    assert tts_service.spoken_text("参考答案一：执行力强[1]。") == "执行力强。"
    assert tts_service.spoken_text("**要点**[1][2]说明。") == "要点说明。"
    assert tts_service.spoken_text("普通回答。") == "普通回答。"
    assert tts_service.spoken_text("【1】仅编号。") == "仅编号。"
    # 前缀清洗按句锚定：多句文本交给 synthesize_sentences 逐句清洗
    assert tts_service.spoken_text("先沟通。参考答案二：再执行。") == "先沟通。参考答案二：再执行。"


def test_synthesize_sentences_cleans_each_sentence(monkeypatch):
    calls = []

    def fake(text, voice):
        calls.append(text)
        return b"mp3"

    monkeypatch.setattr(tts_service, "_communicate", fake)
    out = list(tts_service.synthesize_sentences("参考答案：先沟通[1]。**参考答案二：**再执行。"))
    assert [s for s, _ in out] == ["先沟通。", "再执行。"]  # 逐句清洗后才合成
    assert calls == ["先沟通。", "再执行。"]


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


def test_synthesize_timed_returns_marks_and_caches(monkeypatch):
    """口型路径：返回 (mp3, 词级时间轴)，与字节路径共用缓存键但各自缓存。"""
    calls = []

    def fake(text, voice):
        calls.append(text)
        marks = [{"text": "你", "t0": 0.0, "t1": 0.2}, {"text": "好", "t0": 0.2, "t1": 0.45}]
        return b"mp3-timed", marks

    monkeypatch.setattr(tts_service, "_communicate_timed", fake)
    data, marks = tts_service.synthesize_timed("你好")
    assert data == b"mp3-timed"
    assert [m["text"] for m in marks] == ["你", "好"]
    assert marks[1]["t0"] == 0.2
    # 命中缓存不再调用合成
    again, marks2 = tts_service.synthesize_timed("你好")
    assert again == b"mp3-timed" and marks2 == marks
    assert calls == ["你好"]


def test_synthesize_timed_retry_then_raise(monkeypatch):
    def boom(text, voice):
        raise RuntimeError("网络失败")

    monkeypatch.setattr(tts_service, "_communicate_timed", boom)
    with pytest.raises(TTSUnavailableError):
        tts_service.synthesize_timed("你好")


def test_synthesize_timed_separate_cache_from_bytes_path(monkeypatch):
    """两条路径缓存互不污染：字节路径命中不会让口型路径拿到空时间轴。"""
    monkeypatch.setattr(tts_service, "_communicate", lambda t, v: b"plain")
    monkeypatch.setattr(tts_service, "_communicate_timed",
                        lambda t, v: (b"timed", [{"text": "你", "t0": 0.0, "t1": 0.3}]))
    assert tts_service.synthesize("你好") == b"plain"
    data, marks = tts_service.synthesize_timed("你好")
    assert data == b"timed" and len(marks) == 1
    assert tts_service.synthesize("你好") == b"plain"
