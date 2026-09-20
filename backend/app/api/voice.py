# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""数字人语音接口：WS 语音问答全链路 + HTTP TTS（打字朗读，Task 5）。

WS 协议按设计文档 §5；语音流水线在独立线程消费同步生成器（answer_events/转写/TTS），
经 asyncio.Queue 转发回 WS，避免阻塞事件循环；cancel 以 threading.Event 贯穿各阶段。
"""
import asyncio
import base64
import logging
import threading

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..core.security import decode_token
from ..db import get_db
from ..models.user import User
from ..services import kb_service
from ..services.asr_service import ASRUnavailableError, transcribe
from ..services.tts_service import TTSUnavailableError, split_sentences, synthesize, synthesize_sentences

router = APIRouter()
logger = logging.getLogger("voice")


def _ends_term(text: str) -> bool:
    """缓冲区末尾是否为句末标点（该句已完整）。"""
    return text.rstrip()[-1:] in "。！？；"


def _tail(parts: list[str]) -> str:
    """句级切分后剩余未完结的尾部片段（缓冲区以句末标点结尾时为空）。"""
    return parts[-1] if parts else ""


async def _ws_user(ws: WebSocket, db: Session) -> User | None:
    """首消息 auth 鉴权：{"type":"auth","token":JWT}。失败回 error 并 close(4401)，返回 None。"""
    try:
        msg = await ws.receive_json()
    except (WebSocketDisconnect, ValueError):
        return None
    if msg.get("type") != "auth":
        await ws.send_json({"type": "error", "message": "请先发送 auth 消息"})
        await ws.close(code=4401)
        return None
    try:
        payload = decode_token(msg["token"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        user = None
    if user is None:
        await ws.send_json({"type": "error", "message": "登录已过期，请重新登录"})
        await ws.close(code=4401)
        return None
    return user


def _pipeline(wav: bytes, user: User, db: Session, cancel: threading.Event, emit) -> None:
    """语音问答流水线（独立线程）：转写 → answer_events → 句级交错 TTS；emit 线程安全入队。

    边生成边播（设计文档 §3）：delta 流中句末标点落句即合成下发；合成耗时（单句约
    0.3~1s）会短暂阻塞 LLM 流消费，聊天框文本有轻微停顿，属演示可接受换取的
    首句播报低延迟。单句合成失败静默跳过（§6 降级）。
    """
    try:
        emit({"type": "status", "state": "transcribing"})
        text = transcribe(wav)
        if cancel.is_set():
            emit({"type": "status", "state": "cancelled"})
            return
        if not text:
            emit({"type": "error", "message": "未识别到语音内容"})
            return
        emit({"type": "transcript", "text": text})
        emit({"type": "status", "state": "thinking"})
        buf = ""
        seq = 0

        def synth_sentence(sentence: str) -> None:
            nonlocal seq
            if cancel.is_set():
                return
            try:
                mp3 = synthesize(sentence)
            except TTSUnavailableError:
                return  # 单句失败静默跳过
            seq += 1
            emit({"type": "audio", "seq": seq,
                  "data": base64.b64encode(mp3).decode("ascii")})

        for event, data in kb_service.answer_events(text, user, db):
            if cancel.is_set():
                return
            if event == "citations":
                emit({"type": "citations", "items": data})
            elif event == "delta":
                emit({"type": "delta", "text": data["text"]})
                buf += data["text"]
                if any(t in buf for t in "。！？；\n"):
                    parts = split_sentences(buf)
                    complete = parts if _ends_term(buf) else parts[:-1]
                    for sentence in complete:
                        synth_sentence(sentence)
                    buf = _tail(parts) if not _ends_term(buf) else ""
            elif event == "error":
                emit({"type": "error", "message": data["message"]})
                return
        # done 后清尾：剩余未完结片段整段合成
        for sentence, mp3 in synthesize_sentences(buf):
            if cancel.is_set():
                return
            seq += 1
            emit({"type": "audio", "seq": seq,
                  "data": base64.b64encode(mp3).decode("ascii")})
        emit({"type": "done", "audio_total": seq})
    except ASRUnavailableError as exc:
        emit({"type": "error", "message": str(exc)})
    except Exception:
        logger.exception("语音问答流水线异常")
        emit({"type": "error", "message": "语音问答服务异常，请稍后重试"})


@router.websocket("/chat")
async def voice_chat(ws: WebSocket, db: Session = Depends(get_db)):
    """WS 语音问答：auth → ready；audio 触发流水线（同一时刻仅一条）；cancel 打断。"""
    await ws.accept()
    user = await _ws_user(ws, db)
    if user is None:
        return
    await ws.send_json({"type": "status", "state": "ready"})
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    cancel = threading.Event()
    drain_task: asyncio.Task | None = None

    def emit(item: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    async def drain() -> None:
        while True:
            item = await queue.get()
            if item is None:
                return
            try:
                await ws.send_json(item)
            except WebSocketDisconnect:
                return

    def run_pipeline(wav: bytes) -> None:
        try:
            _pipeline(wav, user, db, cancel, emit)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except ValueError:
                await ws.send_json({"type": "error", "message": "消息格式错误"})
                continue
            if msg.get("type") == "cancel":
                cancel.set()
            elif msg.get("type") == "audio":
                if drain_task is not None and not drain_task.done():
                    await ws.send_json({"type": "error", "message": "正在处理中，请稍候或先打断"})
                    continue
                data = msg.get("data")
                if not isinstance(data, str):
                    await ws.send_json({"type": "error", "message": "audio 消息缺少 data 字段"})
                    continue
                try:
                    wav = base64.b64decode(data, validate=True)
                except Exception:
                    await ws.send_json({"type": "error", "message": "音频数据编码无效"})
                    continue
                cancel.clear()
                drain_task = asyncio.create_task(drain())
                threading.Thread(target=run_pipeline, args=(wav,),
                                 daemon=True, name="voice-pipeline").start()
    finally:
        cancel.set()
        if drain_task is not None and not drain_task.done():
            drain_task.cancel()
