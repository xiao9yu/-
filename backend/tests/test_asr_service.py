# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""ASR 服务测试：模型懒加载/失败哨兵/转写（全部 mock，不加载真实 funasr）。"""
import pytest

from app.services import asr_service


class FakeModel:
    """funasr AutoModel 替身：generate 返回其构造时固定的结果，并记录调用参数。"""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate(self, input=None, **kwargs):
        self.calls.append((input, kwargs))
        return [{"text": self.text}]


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    """每个用例重置模块级单例状态。"""
    monkeypatch.setattr(asr_service, "_model", None)
    monkeypatch.setattr(asr_service, "_loaded", False)


def test_transcribe_returns_text(monkeypatch):
    monkeypatch.setattr(asr_service, "_load_model", lambda: FakeModel("  你好世界  "))
    monkeypatch.setattr(asr_service, "hotword_correct", lambda t: t)
    assert asr_service.transcribe(b"wav-bytes") == "你好世界"


def test_transcribe_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(asr_service, "_load_model", lambda: FakeModel(""))
    monkeypatch.setattr(asr_service, "hotword_correct", lambda t: t)
    assert asr_service.transcribe(b"wav-bytes") == ""


def test_transcribe_despaces_cjk_but_keeps_latin_words(monkeypatch):
    """paraformer-zh 输出为逐字空格分隔：汉字之间空格去掉（token 痕迹），
    挨着拉丁词的边界空格保留——"AI Agent" 不能被并成 "AIAgent"。"""
    monkeypatch.setattr(asr_service, "_load_model",
                        lambda: FakeModel("你 好 AI Agent 回 答"))
    monkeypatch.setattr(asr_service, "hotword_correct", lambda t: t)
    assert asr_service.transcribe(b"wav-bytes") == "你好 AI Agent 回答"


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
    monkeypatch.setattr(asr_service, "hotword_correct", lambda t: t)
    asr_service.transcribe(b"a")
    asr_service.transcribe(b"b")
    assert len(calls) == 1


def test_transcribe_applies_hotword_correction_after_despace(monkeypatch):
    """热词纠正改为转写**之后**在文本上执行（不再作为 generate 的 kwarg）：
    带空格时 matcher 只能替换前半截留下尾巴，连续文本才能整词命中。"""
    model = FakeModel("项 链 召 回")
    monkeypatch.setattr(asr_service, "_load_model", lambda: model)
    fixed: list[str] = []
    monkeypatch.setattr(asr_service, "hotword_correct", lambda t: fixed.append(t) or "向量召回")
    assert asr_service.transcribe(b"wav-bytes") == "向量召回"
    assert model.calls[0][1] == {}          # generate 不再收任何热词参数
    assert fixed == ["项链召回"]            # 纠错拿到的是去空格后的连续文本


def test_transcribe_hotword_disabled_returns_despaced_only(monkeypatch):
    """asr_hotwords 置空 = 关闭热词：只去空格不纠错，行为与无热词版本一致。"""
    model = FakeModel("你 好")
    monkeypatch.setattr(asr_service, "_load_model", lambda: model)
    monkeypatch.setattr(asr_service.settings, "asr_hotwords", "")
    assert asr_service.transcribe(b"wav-bytes") == "你好"


def test_hotword_correct_disabled_returns_original(monkeypatch):
    monkeypatch.setattr(asr_service.settings, "asr_hotwords", "")
    assert asr_service.hotword_correct("项链召回") == "项链召回"


def test_hotword_correct_delegates_to_funasr_utility(monkeypatch):
    """纠错委托给 funasr 的文本级 postprocess 工具；其异常被吞掉回退原文。"""
    calls: list[tuple] = []

    def fake_apply(text, terms):
        calls.append((text, terms))
        return "向量召回"

    monkeypatch.setattr(asr_service, "_apply_hotword_postprocess", fake_apply)
    assert asr_service.hotword_correct("项链召回") == "向量召回"
    assert calls[0] == ("项链召回", asr_service.hotword_terms())


def test_hotword_correct_failure_returns_original(monkeypatch):
    def boom(text, terms):
        raise RuntimeError("funasr 内部错误")

    monkeypatch.setattr(asr_service, "_apply_hotword_postprocess", boom)
    assert asr_service.hotword_correct("项链召回") == "项链召回"


def test_hotword_terms_dedupes_and_strips(monkeypatch):
    monkeypatch.setattr(asr_service.settings, "asr_hotwords", " 精排 , 精排 ,, 向量召回 ")
    assert asr_service.hotword_terms() == ["精排", "向量召回"]
    monkeypatch.setattr(asr_service.settings, "asr_hotwords", "")
    assert asr_service.hotword_terms() == []
