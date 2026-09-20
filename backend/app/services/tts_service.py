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


_CITE_RE = re.compile(r"[\[【]\s*\d+(?:\s*[,，、]\s*\d+)*\s*[\]】]")
_REF_PREFIX_RE = re.compile(r"^\s*(?:参考答案|参考思路|回答思路|答案)(?:\s*[一二三四五六七八九十\d]+)?\s*[:：]\s*")
_MD_RE = re.compile(r"[*#`]+")


def spoken_text(text: str) -> str:
    """朗读文本清洗：去引用编号 [n]、markdown 强调符与"参考答案："式前缀。

    显示文本（字幕）保留引用编号供溯源标签，朗读时编号与"参考答案"字样纯属噪音，
    故仅清洗合成输入，不影响展示与引用数据。
    """
    text = _MD_RE.sub("", text)
    text = _CITE_RE.sub("", text)
    while True:
        stripped = _REF_PREFIX_RE.sub("", text)
        if stripped == text:
            return text
        text = stripped


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
    """单次合成（测试 monkeypatch 的 seam；真实 edge_tts 仅在此懒导入）。

    edge-tts 7.x 的 save_sync(audio_fname) 必传文件名且写盘、不返回字节（旧版
    无参调用返回字节，本项目曾按旧版 API 调用 → 运行时 TypeError 被吞成 502）；
    改用 stream() 流式收集 audio 分片，6.x/7.x 版本行为一致。
    """
    import asyncio
    import edge_tts

    async def _collect() -> bytes:
        com = edge_tts.Communicate(text, voice, pitch=settings.tts_pitch)
        buf = bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        if not buf:
            raise ValueError("edge-tts 返回空音频")
        return bytes(buf)

    try:
        return asyncio.run(_collect())
    except RuntimeError:
        # 在运行中的事件循环上被调用时，asyncio.run 会抛 RuntimeError：借线程另起 loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _collect()).result()


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
    """逐句合成生成器（语音问答路径）：(句子, mp3 bytes) 逐句产出；单句失败跳过。

    逐句先经 spoken_text 清洗（去 [n] 编号与"参考答案："前缀），朗读内容不再念出
    引用标记；返回的句子为清洗后文本，与合成内容一致。
    """
    v = voice or settings.tts_voice
    for sentence in split_sentences(text):
        sentence = spoken_text(sentence)
        if not sentence.strip():
            continue  # 清洗后为空（如纯编号句）不合成
        try:
            yield sentence, synthesize(sentence, v)
        except TTSUnavailableError:
            logger.warning("单句合成失败，跳过：%.30s", sentence)
