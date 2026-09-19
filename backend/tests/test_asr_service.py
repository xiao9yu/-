# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""ASR 服务测试：模型懒加载/失败哨兵/转写（全部 mock，不加载真实 funasr）。"""
import pytest

from app.services import asr_service


class FakeModel:
    """funasr AutoModel 替身：generate 返回其构造时固定的结果。"""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate(self, input=None):
        self.calls.append(input)
        return [{"text": self.text}]


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    """每个用例重置模块级单例状态。"""
    monkeypatch.setattr(asr_service, "_model", None)
    monkeypatch.setattr(asr_service, "_loaded", False)


def test_transcribe_returns_text(monkeypatch):
    monkeypatch.setattr(asr_service, "_load_model", lambda: FakeModel("  你好世界  "))
    assert asr_service.transcribe(b"wav-bytes") == "你好世界"


def test_transcribe_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(asr_service, "_load_model", lambda: FakeModel(""))
    assert asr_service.transcribe(b"wav-bytes") == ""


def test_model_load_failure_caches_none_and_raises(monkeypatch):
    def boom():
        raise RuntimeError("模型下载失败")

    monkeypatch.setattr(asr_service, "_load_model", boom)
    with pytest.raises(asr_service.ASRUnavailableError):
        asr_service.transcribe(b"wav-bytes")
    assert asr_service.get_asr() is None  # 失败哨兵已缓存，不再重试加载


def test_model_loaded_once(monkeypatch):
    calls = []

    def load():
        calls.append(1)
        return FakeModel("你好")

    monkeypatch.setattr(asr_service, "_load_model", load)
    asr_service.transcribe(b"a")
    asr_service.transcribe(b"b")
    assert len(calls) == 1
