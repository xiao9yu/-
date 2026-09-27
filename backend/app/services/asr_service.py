# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""ASR 服务：本地 FunASR（paraformer-zh）离线语音转写。

懒加载单例 + lifespan 预热（main.py），失败缓存 None 哨兵：模型未下载/加载失败时
语音输入提示打字，文字功能零影响。funasr 经 modelscope 取模型（本机 HF 不可达），
disable_update=True 不联网检查更新。
"""
import logging
import re
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


def hotword_terms() -> list[str]:
    """领域热词列表（去重、去空）；settings.asr_hotwords 置空即关闭。"""
    return list(dict.fromkeys(t.strip() for t in settings.asr_hotwords.split(",") if t.strip()))


def hotword_correct(text: str) -> str:
    """文本级热词纠错（批量与流式共用）：funasr 的 postprocess_hotwords 工具。

    paraformer-zh 没有模型级 hotword 偏置（该能力只在 seaco/contextual 变体上），
    两条路径都改为对**最终文本**做拼音模糊纠正——通用模型把"向量召回"听成
    "项链召回"这类领域词错误，会按热词表纠回（依赖 pypinyin + rapidfuzz）。
    纠错失败静默返回原文：热词是锦上添花，不能因它把整段转写变成异常。
    """
    terms = hotword_terms()
    if not terms:
        return text
    try:
        return _apply_hotword_postprocess(text, terms)
    except Exception:
        logger.exception("热词纠错失败（回退原文）")
        return text


def _apply_hotword_postprocess(text: str, terms: list[str]) -> str:
    """funasr 文本级纠正的调用点（测试 monkeypatch 的 seam）：
    入参去空格后的整句文本，返回纠正后的整句文本（未命中返回原句）。"""
    from funasr.utils.postprocess_hotwords import apply_postprocess_hotwords_to_results
    results = apply_postprocess_hotwords_to_results(
        [{"text": text}], {"postprocess_hotwords": terms})
    fixed = str(results[0].get("text") or "").strip()
    return fixed or text


_CJK_SPACE = re.compile(r"(?<=[一-鿿])\s+(?=[一-鿿])")


def transcribe(wav_bytes: bytes) -> str:
    """16k 单声道 WAV 字节 → 转写文本。模型未就绪抛 ASRUnavailableError；空结果返回 ""。

    paraformer-zh 输出为逐字空格分隔（token 痕迹）：先去除**汉字之间**的空格
    （拉丁词间空格保留，"AI Agent" 不会被并成 "AIAgent"），再做热词纠错——
    matcher 的滑动窗口按目标词长度 ±1 扫原始文本，带空格时 "向 量 召 回" 会被
    切碎、只替换前半截留下尾巴（"向量召回 回"），连续文本上才能整词匹配。
    """
    model = get_asr()
    if model is None:
        raise ASRUnavailableError("语音识别未就绪，请打字提问")
    results = model.generate(input=wav_bytes)
    if not results:
        return ""
    text = _CJK_SPACE.sub("", str(results[0].get("text") or "").strip())
    return hotword_correct(text)
