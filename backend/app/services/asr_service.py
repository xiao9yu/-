# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""ASR 服务：本地 FunASR（paraformer-zh）离线语音转写。

懒加载单例 + lifespan 预热（main.py），失败缓存 None 哨兵：模型未下载/加载失败时
语音输入提示打字，文字功能零影响。funasr 经 modelscope 取模型（本机 HF 不可达），
disable_update=True 不联网检查更新。
"""
import logging
import threading

from ..config import settings

logger = logging.getLogger("asr")

_model = None       # AutoModel 实例；加载失败缓存 None 哨兵
_loaded = False
_lock = threading.Lock()


class ASRUnavailableError(Exception):
    """ASR 模型未就绪（未下载/加载失败）。"""


def _load_model():
    """加载 FunASR 模型（测试 monkeypatch 的 seam；真实 funasr 仅在此懒导入）。"""
    from funasr import AutoModel
    return AutoModel(model=settings.asr_model, disable_update=True)


def get_asr():
    """懒加载单例：成功缓存模型，失败缓存 None 哨兵（仿 rerank get_reranker）。"""
    global _model, _loaded
    with _lock:
        if not _loaded:
            _loaded = True
            try:
                _model = _load_model()
                logger.info("ASR 模型加载完成（%s）", settings.asr_model)
            except Exception as exc:
                _model = None
                logger.warning("ASR 模型加载失败（语音输入将提示打字）：%s", exc)
        return _model


def transcribe(wav_bytes: bytes) -> str:
    """16k 单声道 WAV 字节 → 转写文本。模型未就绪抛 ASRUnavailableError；空结果返回 ""。"""
    model = get_asr()
    if model is None:
        raise ASRUnavailableError("语音识别未就绪，请打字提问")
    results = model.generate(input=wav_bytes)
    if not results:
        return ""
    return str(results[0].get("text") or "").strip()
