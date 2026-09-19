# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""TTS 服务：edge-tts 在线合成（分句 + LRU 缓存 + 重试降级）。

edge-tts 属在线服务（端点已验证可达）：合成失败重试 1 次后抛 TTSUnavailableError，
语音链路逐句跳过、回答文字不受影响（设计文档 §6 降级口径）。
"""
import hashlib
import logging
import re
import threading
from collections import OrderedDict

from ..config import settings

logger = logging.getLogger("tts")

_SENT_SPLIT = re.compile(r"(?<=[。！？；])\s*|\n+")
_MAX_SENT = 120      # 单句超长按逗号再切
_CACHE_MAX = 50

_cache: OrderedDict[str, bytes] = OrderedDict()
_lock = threading.Lock()


class TTSUnavailableError(Exception):
    """TTS 不可用（网络/服务失败重试后仍失败）。"""


def split_sentences(text: str) -> list[str]:
    """中文标点/换行分句（保留句末标点，利于合成韵律）；超长句按逗号再切；纯标点句丢弃。"""
    raw = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    raw = [p for p in raw if any(ch not in "。！？；，" for ch in p)]
    parts = []
    for p in raw:
        if len(p) <= _MAX_SENT:
            parts.append(p)
            continue
        for sub in re.split(r"(?<=，)", p):
            sub = sub.strip()
            if sub:
                parts.append(sub)
    return parts


def _communicate(text: str, voice: str) -> bytes:
    """单次合成（测试 monkeypatch 的 seam；真实 edge_tts 仅在此懒导入）。"""
    import edge_tts
    return edge_tts.Communicate(text, voice).save_sync()


def _key(text: str, voice: str) -> str:
    return hashlib.md5(f"{voice}\x00{text}".encode("utf-8")).hexdigest()


def synthesize(text: str, voice: str | None = None) -> bytes:
    """整段合成 mp3（打字朗读路径）。缓存命中直返；失败重试 1 次后抛 TTSUnavailableError。"""
    v = voice or settings.tts_voice
    k = _key(text, v)
    with _lock:
        if k in _cache:
            return _cache[k]
    try:
        data = _communicate(text, v)
    except Exception:
        try:
            data = _communicate(text, v)
        except Exception as exc:
            raise TTSUnavailableError("语音合成服务不可用") from exc
    with _lock:
        _cache[k] = data
        _cache.move_to_end(k)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return data


def synthesize_sentences(text: str, voice: str | None = None):
    """逐句合成生成器（语音问答路径）：(句子, mp3 bytes) 逐句产出；单句失败跳过。"""
    v = voice or settings.tts_voice
    for sentence in split_sentences(text):
        try:
            yield sentence, synthesize(sentence, v)
        except TTSUnavailableError:
            logger.warning("单句合成失败，跳过：%.30s", sentence)
