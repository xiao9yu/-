# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""流式语音前端测试：VAD 端点检测、增量转写、批量降级（全 mock，不加载真实模型）。"""
import numpy as np
import pytest

from app.services import asr_stream


class FakeVad:
    """按脚本逐次返回端点结果：脚本元素即一次 generate 的 value（[[beg,end], ...]）。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def generate(self, input=None, cache=None, is_final=False, chunk_size=None):
        self.calls.append({"is_final": is_final, "samples": int(len(input))})
        value = self.script.pop(0) if self.script else []
        return [{"value": value}]


class FakeStreamAsr:
    """逐次返回增量文本（FunASR 流式接口返回的是累计文本）。"""

    def __init__(self, texts):
        self.texts = list(texts)
        self.final_calls = 0

    def generate(self, input=None, cache=None, is_final=False, chunk_size=None,
                 encoder_chunk_look_back=None, decoder_chunk_look_back=None):
        if is_final:
            self.final_calls += 1
        return [{"text": self.texts.pop(0) if self.texts else ""}]


def _pcm(ms: int, amp: int = 1000) -> bytes:
    n = asr_stream.SAMPLE_RATE * ms // 1000
    return (np.ones(n, dtype="<i2") * amp).tobytes()


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch):
    """流式模型是进程级懒加载单例：每个用例前后复位，避免相互污染。"""
    monkeypatch.setattr(asr_stream, "_loaded", False)
    monkeypatch.setattr(asr_stream, "_vad_model", None)
    monkeypatch.setattr(asr_stream, "_stream_model", None)
    yield


def _preload(monkeypatch, vad, asr):
    monkeypatch.setattr(asr_stream, "_load_vad_model", lambda: vad)
    monkeypatch.setattr(asr_stream, "_load_stream_model", lambda: asr)
    asr_stream.preload()


def test_available_false_before_preload_and_without_vad(monkeypatch):
    assert asr_stream.available() is False           # 未预热：不触发加载，直接不可用
    _preload(monkeypatch, None, FakeStreamAsr([]))   # VAD 加载失败
    assert asr_stream.available() is False
    monkeypatch.setattr(asr_stream, "_loaded", False)
    monkeypatch.setattr(asr_stream, "_vad_model", None)
    monkeypatch.setattr(asr_stream.settings, "voice_stream_enabled", False)
    _preload(monkeypatch, FakeVad([]), FakeStreamAsr([]))
    assert asr_stream.available() is False           # 总开关关闭时不论模型是否就绪都不可用


def test_available_true_when_vad_loaded(monkeypatch):
    _preload(monkeypatch, FakeVad([]), FakeStreamAsr([]))
    assert asr_stream.available() is True


def test_feed_emits_partial_then_segment_end(monkeypatch):
    """说话中出 partial，VAD 判定端点后出 segment_end（文本取自流式 ASR 收尾）。"""
    asr = FakeStreamAsr(["你", "你好"])
    _preload(monkeypatch, FakeVad([[[0, -1]], [], [], [[0, 600]]]), asr)
    rec = asr_stream.StreamingRecognizer()
    got = []
    for _ in range(4):
        got += rec.feed(_pcm(200))
    assert got == [("partial", {"text": "你"}),
                   ("segment_end", {"text": "你好", "duration_ms": 800})]
    assert asr.final_calls == 1
    assert rec.speaking is False and rec.partial == ""


def test_preroll_restores_speech_onset(monkeypatch):
    """段首预滚：VAD 在第 2 帧才判定起说，但段内已含第 1 帧（字头不被吃掉）。"""
    _preload(monkeypatch, FakeVad([[], [[0, -1]]]), FakeStreamAsr([]))
    rec = asr_stream.StreamingRecognizer()
    rec.feed(_pcm(200))
    assert rec.speaking is False
    rec.feed(_pcm(200))
    assert rec.speaking is True
    assert rec._seg_ms == 400      # 200ms（判定帧）+ 200ms（预滚），而非仅 200ms


def test_batch_fallback_when_stream_asr_missing(monkeypatch):
    """流式 ASR 不可用而 VAD 可用：端点命中后回退批量转写，段落仍能闭环。"""
    _preload(monkeypatch, FakeVad([[[0, -1]], [[0, 400]]]), None)
    monkeypatch.setattr("app.services.asr_service.transcribe", lambda wav: "批量转写结果")
    rec = asr_stream.StreamingRecognizer()
    got = rec.feed(_pcm(200)) + rec.feed(_pcm(200))
    assert [e for e, _ in got] == ["segment_end"]
    assert got[0][1]["text"] == "批量转写结果"


def test_batch_fallback_swallows_asr_unavailable(monkeypatch):
    """批量模型也没就绪：段落丢弃但不抛异常（上层不因此报错）。"""
    from app.services.asr_service import ASRUnavailableError

    def boom(wav):
        raise ASRUnavailableError("未就绪")

    _preload(monkeypatch, FakeVad([[[0, -1]], [[0, 400]]]), None)
    monkeypatch.setattr("app.services.asr_service.transcribe", boom)
    rec = asr_stream.StreamingRecognizer()
    assert rec.feed(_pcm(200)) + rec.feed(_pcm(200)) == []


def test_finish_flushes_open_segment(monkeypatch):
    """仍处于说话中时 finish() 强制收尾，避免用户不松口就丢内容。"""
    asr = FakeStreamAsr(["半句话"])
    _preload(monkeypatch, FakeVad([[[0, -1]]]), asr)
    rec = asr_stream.StreamingRecognizer()
    rec.feed(_pcm(200))
    assert rec.speaking is True
    got = rec.finish()
    assert got == [("segment_end", {"text": "半句话", "duration_ms": 200})]
    assert asr.final_calls == 1


def test_feed_ignores_vad_inference_error(monkeypatch):
    """单帧 VAD 推理异常不中断会话：跳过该帧继续（宁可晚断不可断错）。"""
    class BoomVad(FakeVad):
        def generate(self, *a, **k):
            raise RuntimeError("推理失败")

    _preload(monkeypatch, BoomVad([]), FakeStreamAsr([]))
    rec = asr_stream.StreamingRecognizer()
    assert rec.feed(_pcm(200)) == []
    assert rec.speaking is False


def test_vad_segments_parses_and_skips_malformed():
    assert asr_stream._vad_segments([{"value": [[0, -1], [500, 1200]]}]) == [(0, -1), (500, 1200)]
    assert asr_stream._vad_segments([{"value": None}]) == []
    assert asr_stream._vad_segments([]) == []
    assert asr_stream._vad_segments([{"value": [[1], "bad"]}]) == []


def test_pcm16_to_float_scales_and_tolerates_odd_length():
    arr = asr_stream._pcm16_to_float((np.array([32767, -32768], dtype="<i2")).tobytes())
    assert arr.dtype == np.float32
    assert arr[0] == pytest.approx(1.0, abs=1e-4) and arr[1] == pytest.approx(-1.0, abs=1e-4)
    assert asr_stream._pcm16_to_float(b"\x01\x02\x03").size == 1   # 奇数长度截掉半字节


def test_float_to_wav16_roundtrip_header():
    samples = np.zeros(asr_stream.SAMPLE_RATE // 10, dtype=np.float32)
    wav = asr_stream._float_to_wav16(samples)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert b"fmt " in wav[:20]
