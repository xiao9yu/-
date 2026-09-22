# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""数字人语音接口：WS 语音问答（按住说话 + 流式自然对话）+ HTTP TTS。

WS 协议（服务端 → 客户端）
  status      ready / transcribing / thinking / listening / cancelled
  transcript  本轮（或本段）最终转写文本
  partial     流式模式：边说边上屏的增量转写
  session     本轮归属的会话 {id, turns}（多轮上下文与引用延续的凭据）
  citations / delta / audio / done   与设计文档 §5 一致；audio 额外带 marks（口型时间轴）
  segment_done  流式模式：单个语音段问答播报完毕（会话不结束）
  error

WS 协议（客户端 → 服务端）
  auth {token, session_id?}          首帧鉴权；session_id 可选，续接同一条会话
  audio {data}                       按住说话：整段 16k WAV（base64）
  stream_start / stream_chunk {data: PCM16 16k} / stream_end   流式自然对话
  interrupt                          只中断本轮回答（自然对话里"抢话"）
  cancel                             打断并结束整场会话

线程模型：语音流水线与流式识别会话都在独立线程消费同步生成器，经 asyncio.Queue
转发回 WS；cancel 用 threading.Event 贯穿各阶段。线程内直接使用请求级 Session——
WS 连接内同一时刻只有一个 worker 在用，且收尾时 join 等待其退出（见 voice_chat finally），
不存在会话级并发使用。
"""
import asyncio
import base64
import logging
import queue
import threading

from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..core.security import decode_token
from ..db import get_db
from ..models.chat import ChatSession
from ..models.user import User
from ..services import asr_stream, chat_service, kb_service
from ..services.asr_service import ASRUnavailableError, transcribe
from ..services.tts_service import (
    TTSUnavailableError, spoken_text, split_sentences, synthesize, synthesize_timed,
)
from .deps import get_current_user

router = APIRouter()
logger = logging.getLogger("voice")

WORKER_JOIN_TIMEOUT = 5.0     # WS 收尾等待 worker 退出的上限（避免 session 被提前关闭）
_FRAME_QUEUE_MAX = 300        # 流式 PCM 帧队列上限（约 30s 音频），防客户端狂发撑爆内存


def _ends_term(text: str) -> bool:
    """缓冲区末尾是否为句末标点（该句已完整）。"""
    return text.rstrip()[-1:] in "。！？；"


class _AnyCancel:
    """组合取消信号：会话级 cancel 或"仅中断本轮回答"的 answer_cancel 任一置位即取消。

    流式自然对话需要区分两种打断：结束整场会话（cancel）与"她说太长了，我现在就想插话"
    （answer_cancel）。把两层信号合成一个 is_set() 接口，_answer_and_speak 不必感知区别。
    """

    def __init__(self, *flags: threading.Event):
        self._flags = flags

    def is_set(self) -> bool:
        return any(f.is_set() for f in self._flags)


def _tail(parts: list[str]) -> str:
    """句级切分后剩余未完结的尾部片段（缓冲区以句末标点结尾时为空）。"""
    return parts[-1] if parts else ""


async def _ws_user(ws: WebSocket, db: Session) -> tuple[User | None, int | None]:
    """首消息 auth 鉴权：{"type":"auth","token":JWT,"session_id":?}。

    失败回 error 并 close(4401)，返回 (None, None)；成功返回 (user, session_id)。
    """
    try:
        msg = await ws.receive_json()
    except (WebSocketDisconnect, ValueError):
        return None, None
    if msg.get("type") != "auth":
        await ws.send_json({"type": "error", "message": "请先发送 auth 消息"})
        await ws.close(code=4401)
        return None, None
    try:
        payload = decode_token(msg["token"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        user = None
    if user is None:
        await ws.send_json({"type": "error", "message": "登录已过期，请重新登录"})
        await ws.close(code=4401)
        return None, None
    raw = msg.get("session_id")
    try:
        session_id = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        session_id = None
    return user, session_id


# ---------- 会话上下文 ----------
def _ensure_session(db: Session, user: User, holder: dict, question: str) -> ChatSession | None:
    """惰性定位/新建会话：鉴权时拿到的 session_id 可能为空或已删除，首次提问时才落地。

    失败返回 None（本轮退化为单轮回答），不因会话问题阻断问答。
    """
    if holder.get("session") is not None:
        return holder["session"]
    try:
        session = chat_service.resolve_session(db, user, holder.get("session_id"), question)
    except Exception:
        logger.exception("会话建立失败（本轮按单轮回答）")
        return None
    holder["session"] = session
    return session


# ---------- 语音问答流水线 ----------
def _answer_and_speak(text: str, user: User, db: Session, holder: dict,
                      cancel: threading.Event, emit, *, end_event: str = "done") -> int:
    """转写文本 → answer_events → 句级交错 TTS；返回本轮下发的音频段数。

    边生成边播（设计文档 §3）：delta 流中句末标点落句即合成下发；合成耗时（单句约
    0.3~1s）会短暂阻塞 LLM 流消费，聊天框文本有轻微停顿，属演示可接受换取的
    首句播报低延迟。单句合成失败静默跳过（§6 降级）。

    音频事件带 marks（edge-tts WordBoundary 时间轴）：数字人据此把口型对齐到
    "哪个字正在被念"，而不是只看音量强弱（详见前端 utils/lipsync.ts）。
    """
    session = _ensure_session(db, user, holder, text)
    if session is not None:
        # 先报会话再报"思考中"：前端在答案到达前就知道本轮归属哪条会话，
        # 语音转文字混用时也能把 WS 一路的问答并进同一个会话时间线
        emit({"type": "session", "id": session.id, "turns": session.turns})
    emit({"type": "status", "state": "thinking"})
    seq = 0
    buf = ""

    def synth_sentence(sentence: str) -> None:
        """单句合成 + 下发；清洗后为空或合成失败即跳过（降级不报错）。"""
        nonlocal seq
        if cancel.is_set():
            return
        cleaned = spoken_text(sentence)   # 去 [n] 编号与"参考答案："前缀
        if not cleaned.strip():
            return
        try:
            mp3, marks = synthesize_timed(cleaned)
        except TTSUnavailableError:
            return
        seq += 1
        emit({"type": "audio", "seq": seq, "marks": marks,
              "data": base64.b64encode(mp3).decode("ascii")})

    for event, data in kb_service.answer_events(text, user, db, session=session):
        if cancel.is_set():
            return seq
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
            return seq
    # done 后清尾：剩余未完结片段整段合成
    for sentence in split_sentences(buf):
        if cancel.is_set():
            return seq
        synth_sentence(sentence)
    emit({"type": end_event, "audio_total": seq})
    return seq


def _pipeline(wav: bytes, user: User, db: Session, holder: dict,
              cancel: threading.Event, emit) -> None:
    """按住说话：整段 WAV → 转写 → 问答播报。"""
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
        _answer_and_speak(text, user, db, holder, _AnyCancel(cancel, holder["answer_cancel"]), emit)
    except ASRUnavailableError as exc:
        emit({"type": "error", "message": str(exc)})
    except Exception:
        logger.exception("语音问答流水线异常")
        emit({"type": "error", "message": "语音问答服务异常，请稍后重试"})


def _stream_worker(user: User, db: Session, holder: dict, cancel: threading.Event,
                   emit, frames: "queue.Queue[bytes | None]",
                   stop_flag: threading.Event) -> None:
    """流式自然对话 worker：VAD 端点检测 + 增量转写 → 端点命中即问答播报。

    回答期间丢弃麦克风帧（不做全双工）：扬声器播报会被麦克风收回形成自问自答，
    浏览器端回声消除不保证干净，因此选择"朵娅说话时不听"这一保守但可用的策略。
    """
    rec = asr_stream.StreamingRecognizer()
    total = 0

    def handle(events) -> None:
        nonlocal total
        for ev, data in events:
            if cancel.is_set():
                return
            if ev == "partial":
                emit({"type": "partial", "text": data["text"]})
            elif ev == "segment_end":
                emit({"type": "transcript", "text": data["text"]})
                holder["answering"] = True
                holder["answer_cancel"].clear()     # 新一轮回答：清掉上一轮的打断标记
                try:
                    total += _answer_and_speak(
                        data["text"], user, db, holder,
                        _AnyCancel(cancel, holder["answer_cancel"]), emit,
                        end_event="segment_done")
                finally:
                    holder["answering"] = False
                if not cancel.is_set():
                    emit({"type": "status", "state": "listening"})

    try:
        while not stop_flag.is_set() and not cancel.is_set():
            try:
                frame = frames.get(timeout=0.2)
            except queue.Empty:
                continue
            if frame is None:
                break
            if holder.get("answering"):
                continue          # 播报中：丢弃麦克风帧（见 docstring）
            handle(rec.feed(frame))
        if not cancel.is_set():
            handle(rec.finish())
    except Exception:
        logger.exception("流式语音会话异常")
        emit({"type": "error", "message": "流式语音服务异常，请稍后重试"})
    finally:
        emit({"type": "status", "state": "cancelled" if cancel.is_set() else "ready"})


@router.websocket("/chat")
async def voice_chat(ws: WebSocket, db: Session = Depends(get_db)):
    """WS 语音问答：auth → ready；按住说话（audio）/ 流式对话（stream_*）；cancel 打断。"""
    await ws.accept()
    user, session_id = await _ws_user(ws, db)
    if user is None:
        return
    await ws.send_json({"type": "status", "state": "ready"})
    loop = asyncio.get_running_loop()
    queue_out: asyncio.Queue[dict | None] = asyncio.Queue()
    cancel = threading.Event()
    holder: dict = {"session": None, "session_id": session_id, "answering": False,
                    "answer_cancel": threading.Event()}
    drain_task: asyncio.Task | None = None
    worker: threading.Thread | None = None
    frames: "queue.Queue[bytes | None]" = queue.Queue(maxsize=_FRAME_QUEUE_MAX)
    stop_flag = threading.Event()

    def emit(item: dict) -> None:
        loop.call_soon_threadsafe(queue_out.put_nowait, item)

    async def drain() -> None:
        while True:
            item = await queue_out.get()
            if item is None:
                return
            try:
                await ws.send_json(item)
            except WebSocketDisconnect:
                return

    def busy() -> bool:
        return drain_task is not None and not drain_task.done()

    def start_worker(target, args) -> None:
        nonlocal drain_task, worker
        cancel.clear()
        stop_flag.clear()
        drain_task = asyncio.create_task(drain())
        worker = threading.Thread(target=target, args=args, daemon=True, name="voice-worker")
        worker.start()

    def run_pipeline(wav: bytes) -> None:
        try:
            _pipeline(wav, user, db, holder, cancel, emit)
        finally:
            loop.call_soon_threadsafe(queue_out.put_nowait, None)

    def run_stream() -> None:
        try:
            _stream_worker(user, db, holder, cancel, emit, frames, stop_flag)
        finally:
            loop.call_soon_threadsafe(queue_out.put_nowait, None)

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except ValueError:
                await ws.send_json({"type": "error", "message": "消息格式错误"})
                continue
            kind = msg.get("type")
            if kind == "cancel":
                cancel.set()
                stop_flag.set()
                while not frames.empty():        # 唤醒阻塞在 get 上的流式 worker
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        break
                frames.put_nowait(None)
            elif kind == "interrupt":
                # 只中断本轮回答，保留监听（自然对话里"抢话"用）；批量模式效果等同打断当前播报
                holder["answer_cancel"].set()
            elif kind == "audio":
                if busy():
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
                start_worker(run_pipeline, (wav,))
            elif kind == "stream_start":
                if busy():
                    await ws.send_json({"type": "error", "message": "正在处理中，请稍候或先打断"})
                    continue
                if not asr_stream.available():
                    await ws.send_json({
                        "type": "error",
                        "message": "流式语音未就绪，请使用按住说话",
                    })
                    continue
                start_worker(run_stream, ())
                await ws.send_json({"type": "status", "state": "listening"})
            elif kind == "stream_chunk":
                data = msg.get("data")
                if not isinstance(data, str) or worker is None or not worker.is_alive():
                    continue
                try:
                    pcm = base64.b64decode(data, validate=True)
                except Exception:
                    continue
                try:
                    frames.put_nowait(pcm)
                except queue.Full:
                    pass          # 客户端推送快于消费：丢帧保活（避免延迟累积到不可用）
            elif kind == "stream_end":
                stop_flag.set()
                try:
                    frames.put_nowait(None)
                except queue.Full:
                    pass
            else:
                await ws.send_json({"type": "error", "message": f"未知消息类型：{kind}"})
    finally:
        cancel.set()
        stop_flag.set()
        try:
            frames.put_nowait(None)
        except queue.Full:
            pass
        # 等 worker 退出再用关闭 session：避免请求级 Session 被 worker 线程使用中被 close
        if worker is not None and worker.is_alive():
            worker.join(timeout=WORKER_JOIN_TIMEOUT)
        if drain_task is not None and not drain_task.done():
            drain_task.cancel()


class TtsIn(BaseModel):
    text: str


@router.get("/capabilities")
def capabilities(user: User = Depends(get_current_user)):
    """语音能力探测：前端据此决定是否展示"自然对话"模式（模型缺失时自动隐藏）。"""
    return {
        "stream": asr_stream.available(),
        "push_to_talk": True,
        "tts": True,
    }


@router.post("/tts")
def tts(data: TtsIn, user: User = Depends(get_current_user)):
    """打字朗读：整段文本合成 mp3。TTS 不可用回 502（前端 speakText 静默降级）。"""
    text = data.text.strip()
    if not text:
        raise BizError(400, "文本不能为空")
    if len(text) > 2000:
        raise BizError(400, "文本过长（最多 2000 字）")
    try:
        return Response(content=synthesize(text), media_type="audio/mpeg")
    except TTSUnavailableError as exc:
        raise BizError(502, str(exc)) from exc


@router.post("/tts/timed")
def tts_timed(data: TtsIn, user: User = Depends(get_current_user)):
    """打字朗读（带口型时间轴）：返回 {audio: base64, marks: [...]}。

    与 /tts 分开而非加参数：整段 mp3 走二进制响应最省事，口型时间轴必须走 JSON，
    混在一个响应里会让"只要音频"的调用方也背上 base64 膨胀（+33%）。
    """
    text = data.text.strip()
    if not text:
        raise BizError(400, "文本不能为空")
    if len(text) > 2000:
        raise BizError(400, "文本过长（最多 2000 字）")
    try:
        mp3, marks = synthesize_timed(text)
    except TTSUnavailableError as exc:
        raise BizError(502, str(exc)) from exc
    return {"audio": base64.b64encode(mp3).decode("ascii"), "marks": marks}
