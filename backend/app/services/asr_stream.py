# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""流式语音前端：FSMN-VAD 端点检测 + paraformer-zh-streaming 增量转写。

把"按住说话"升级为自然轮次对话的**服务端**实现：前端持续推 16k 单声道 PCM16 帧，
本模块负责
  1) FSMN-VAD 流式判端点（说话起止），替代浏览器 RMS 阈值——阈值法对风扇/键盘噪声
     误触发且对轻声起头不敏感，FSMN 是训练出来的端点模型，鲁棒性不同量级；
  2) 段落内用 paraformer 流式增量转写，逐帧回吐 partial，用户说话时就能看到上屏；
  3) 端点命中即产出 segment_end（该段最终文本），交给上层跑 RAG + TTS。

设计约束：VAD 流式固定 200ms 粒度、ASR 流式固定 600ms 步长（模型内部约束，
由 chunk_size 决定），故本模块内部自行缓冲对齐，调用方可按任意帧长喂入。

降级：流式 ASR 模型不可用而 VAD 可用时，端点命中后回退批量 transcribe（同一进程已
缓存批量模型）；VAD 也不可用则 available() 为 False，上层提示退回答按住说话。
"""
import logging
import threading

import numpy as np

from ..config import settings

logger = logging.getLogger("asr_stream")

SAMPLE_RATE = 16000
VAD_CHUNK_MS = 200                      # FSMN-VAD 流式固定粒度（模型约束）
ASR_CHUNK_SIZE = [0, 10, 5]             # [look_back, chunk, look_ahead]，单位 60ms
ASR_STRIDE_MS = ASR_CHUNK_SIZE[1] * 60  # 600ms 步长
ENC_LOOK_BACK = 4
DEC_LOOK_BACK = 1
PREROLL_MS = 300                        # 段首预滚：VAD 判定起说时补回此前 300ms，避免吃掉字头
POSTROLL_MS = 200                       # 段尾补偿：VAD 判定结束时多留 200ms，避免切掉尾音


def _ms_to_samples(ms: int) -> int:
    return SAMPLE_RATE * ms // 1000


_stream_model = None
_vad_model = None
_loaded = False
_lock = threading.Lock()


def _load_stream_model():
    """加载流式 ASR（测试 monkeypatch 的 seam；真实 funasr 仅在此懒导入）。"""
    from funasr import AutoModel
    return AutoModel(model=settings.asr_stream_model, disable_update=True)


def _load_vad_model():
    """加载 FSMN-VAD（测试 monkeypatch 的 seam）。"""
    from funasr import AutoModel
    return AutoModel(model=settings.vad_model, disable_update=True)


def preload() -> None:
    """懒加载两个流式模型：成功缓存实例，失败缓存 None 哨兵（仿 asr_service.get_asr）。"""
    global _stream_model, _vad_model, _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        for name, loader in (("VAD", _load_vad_model), ("流式 ASR", _load_stream_model)):
            try:
                model = loader()
            except Exception as exc:
                logger.warning("%s 模型加载失败（流式语音将降级）：%s", name, exc)
                model = None
            if name == "VAD":
                _vad_model = model
            else:
                _stream_model = model


def get_vad():
    preload()
    return _vad_model


def get_stream_model():
    preload()
    return _stream_model


def available() -> bool:
    """流式语音会话是否可用：VAD 是端点检测的必需品，缺它则整条流式链路无法闭环。

    只看**已加载**状态、不触发加载：本函数在事件循环里被 WS 消息处理调用，
    原地加载 880MB 流式 ASR 会阻塞整个 loop（其他连接的请求一起卡住）。
    加载交给 main.py 的启动预热线程，预热未完成时前端自动不展示自然对话模式。
    """
    if not settings.voice_stream_enabled:
        return False
    return _vad_model is not None


class StreamingRecognizer:
    """一次语音会话（一次 WS 连接）的流式识别状态机。

    线程约束：非线程安全，应由单个消费线程独占地 feed/finish（WS 侧即流水线线程）。
    """

    def __init__(self):
        self._vad_cache: dict = {}          # FSMN-VAD 流式 cache
        self._vad_buf = np.zeros(0, dtype=np.float32)   # VAD 粒度对齐缓冲
        self._asr_cache: dict | None = None             # 当前段的 ASR cache（段起点重置）
        self._asr_buf = np.zeros(0, dtype=np.float32)   # ASR 步长对齐缓冲
        self._preroll: list[np.ndarray] = []            # 段首预滚样本
        self._preroll_len = 0
        self._seg_audio: list[np.ndarray] = []          # 当前段全部样本（批量降级用）
        self._seg_ms = 0                                # 当前段已累计时长
        self._speaking = False
        self._partial = ""

    # ---------- 对外状态 ----------
    @property
    def speaking(self) -> bool:
        return self._speaking

    @property
    def partial(self) -> str:
        return self._partial

    # ---------- 喂数据 ----------
    def feed(self, pcm16: bytes) -> list[tuple[str, dict]]:
        """喂入 16k 单声道 PCM16 帧，返回本次产生的事件：
        ("partial", {"text": ...}) / ("segment_end", {"text": ..., "duration_ms": ...})
        """
        samples = _pcm16_to_float(pcm16)
        if samples.size == 0:
            return []
        events: list[tuple[str, dict]] = []
        self._push_preroll(samples)
        if self._speaking:
            events += self._feed_asr(samples)
        events += self._feed_vad(samples)
        return events

    def finish(self) -> list[tuple[str, dict]]:
        """收尾：冲刷 VAD/ASR 缓冲，若仍在说话则强制产出一段。"""
        events: list[tuple[str, dict]] = []
        events += self._flush_vad()
        if self._speaking:
            text = self._finalize_asr()
            if text:
                events.append(("segment_end", {"text": text, "duration_ms": self._seg_ms}))
            self._reset_segment()
        return events

    # ---------- 内部实现 ----------
    def _push_preroll(self, samples: np.ndarray) -> None:
        self._preroll.append(samples)
        self._preroll_len += samples.size
        cap = _ms_to_samples(PREROLL_MS)
        while self._preroll_len - self._preroll[0].size >= cap:
            self._preroll_len -= self._preroll.pop(0).size

    def _feed_vad(self, samples: np.ndarray) -> list[tuple[str, dict]]:
        """按 200ms 粒度喂 VAD，解析端点事件（end=-1 表示说话中）。"""
        events: list[tuple[str, dict]] = []
        self._vad_buf = np.concatenate([self._vad_buf, samples])
        step = _ms_to_samples(VAD_CHUNK_MS)
        vad = get_vad()
        while self._vad_buf.size >= step:
            frame, self._vad_buf = self._vad_buf[:step], self._vad_buf[step:]
            if vad is None:
                continue
            try:
                res = vad.generate(input=frame, cache=self._vad_cache,
                                   is_final=False, chunk_size=VAD_CHUNK_MS)
            except Exception:
                # 单帧 VAD 异常不中断会话：标记后按"未检出端点"继续（宁可晚断不可断错）
                logger.exception("VAD 单帧推理失败")
                continue
            for _beg, end in _vad_segments(res):
                if end < 0:
                    self._begin_segment()
                else:
                    events += self._end_segment()
        return events

    def _flush_vad(self) -> list[tuple[str, dict]]:
        vad = get_vad()
        if vad is None or self._vad_buf.size == 0:
            return []
        tail, self._vad_buf = self._vad_buf, np.zeros(0, dtype=np.float32)
        try:
            res = vad.generate(input=tail, cache=self._vad_cache, is_final=True,
                               chunk_size=VAD_CHUNK_MS)
        except Exception:
            logger.exception("VAD 收尾推理失败")
            return []
        return self._end_segment() if any(e >= 0 for _b, e in _vad_segments(res)) else []

    def _begin_segment(self) -> None:
        if self._speaking:
            return
        self._speaking = True
        self._seg_audio = list(self._preroll)     # 预滚补回字头
        self._seg_ms = 0
        self._asr_cache = {}
        self._asr_buf = np.zeros(0, dtype=np.float32)
        self._partial = ""
        lead = np.concatenate(self._seg_audio) if self._seg_audio else np.zeros(0, dtype=np.float32)
        if lead.size:
            self._seg_ms += int(lead.size * 1000 / SAMPLE_RATE)
            self._asr_buf = lead

    def _end_segment(self) -> list[tuple[str, dict]]:
        if not self._speaking:
            return []
        text = self._finalize_asr()
        events: list[tuple[str, dict]] = []
        if text:
            events.append(("segment_end", {"text": text, "duration_ms": self._seg_ms}))
        self._reset_segment()
        return events

    def _reset_segment(self) -> None:
        self._speaking = False
        self._seg_audio = []
        self._seg_ms = 0
        self._asr_cache = None
        self._asr_buf = np.zeros(0, dtype=np.float32)
        self._partial = ""

    def _feed_asr(self, samples: np.ndarray) -> list[tuple[str, dict]]:
        """累计样本并按 600ms 步长喂流式 ASR；不足一步则留到下帧。"""
        self._seg_audio.append(samples)
        self._seg_ms += int(samples.size * 1000 / SAMPLE_RATE)
        if self._asr_cache is None:
            return []
        self._asr_buf = np.concatenate([self._asr_buf, samples])
        step = _ms_to_samples(ASR_STRIDE_MS)
        model = get_stream_model()
        events: list[tuple[str, dict]] = []
        while self._asr_buf.size >= step:
            frame, self._asr_buf = self._asr_buf[:step], self._asr_buf[step:]
            if model is None:
                continue  # 无流式模型：不产出 partial，段末由批量转写兜底
            text = self._asr_generate(model, frame, is_final=False)
            if text and text != self._partial:
                self._partial = text
                events.append(("partial", {"text": text}))
        return events

    def _finalize_asr(self) -> str:
        """段末冲刷：流式模型可用则带剩余样本收尾，否则回退批量转写整段。"""
        model = get_stream_model()
        if model is not None and self._asr_cache is not None:
            tail = self._asr_buf
            self._asr_buf = np.zeros(0, dtype=np.float32)
            text = self._asr_generate(model, tail, is_final=True)
            if text.strip():
                return text.strip()
        return self._batch_fallback()

    def _batch_fallback(self) -> str:
        """批量转写当前段（流式模型缺失时的降级路径；复用 asr_service 已缓存的批量模型）。"""
        if not self._seg_audio:
            return ""
        from .asr_service import ASRUnavailableError, transcribe
        samples = np.concatenate(self._seg_audio)
        try:
            return transcribe(_float_to_wav16(samples)).strip()
        except ASRUnavailableError:
            return ""
        except Exception:
            logger.exception("批量转写降级失败")
            return ""

    def _asr_generate(self, model, frame: np.ndarray, *, is_final: bool) -> str:
        try:
            res = model.generate(
                input=frame, cache=self._asr_cache, is_final=is_final,
                chunk_size=ASR_CHUNK_SIZE,
                encoder_chunk_look_back=ENC_LOOK_BACK,
                decoder_chunk_look_back=DEC_LOOK_BACK,
            )
        except Exception:
            logger.exception("流式 ASR 推理失败")
            return ""
        if not res:
            return ""
        return str(res[0].get("text") or "").strip()


# ---------- 工具 ----------
def _pcm16_to_float(pcm16: bytes) -> np.ndarray:
    """PCM16 小端字节 → float32 [-1,1]（FunASR 流式接口按 soundfile 口径吃 float）。"""
    if len(pcm16) % 2:                      # 奇数长度截掉半字节，避免 frombuffer 抛异常
        pcm16 = pcm16[:-1]
    arr = np.frombuffer(pcm16, dtype="<i2")
    return (arr.astype(np.float32) / 32768.0)


def _float_to_wav16(samples: np.ndarray) -> bytes:
    """float32 [-1,1] → 16k 单声道 PCM16 WAV 字节（批量转写降级用）。"""
    import io
    import wave

    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _vad_segments(res) -> list[tuple[int, int]]:
    """解析 FunASR-VAD 流式返回：value 为 [[beg_ms, end_ms], ...]，end=-1 表示仍在说。"""
    if not res:
        return []
    value = res[0].get("value")
    if not value:
        return []
    out: list[tuple[int, int]] = []
    for item in value:
        try:
            beg, end = int(item[0]), int(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        out.append((beg, end))
    return out
