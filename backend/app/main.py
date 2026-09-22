# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""FastAPI 应用入口。"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import auth, chat, files, kb, learn, prep, voice
from .core.exceptions import register_exception_handlers
from .db import Base, engine
from .services.embeddings import EmbedderError, get_embedder
from .services.rerank import get_reranker

# uvicorn 默认只给 uvicorn.* 配 handler，应用 logger 的 INFO 会静默丢弃；
# basicConfig 给 root 挂 handler，预热/问答等应用日志可见（ERROR 原靠 lastResort 兜底）。
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("main")


def _preheat_models() -> None:
    """后台预热 bge-reranker 与 bge-m3：首次加载（下载/读盘）耗时，不阻塞启动。

    顺序加载避免两个大模型并发读盘/占用内存峰值；嵌入模型未预热时首个上传/问答
    的请求线程会承担分钟级懒加载，期间前端 30s 超时表现为"上传失败/问答无反馈"
    （本机 HF 不可达时逐文件网络重试）。get_reranker 失败缓存 False 哨兵；
    get_embedder 失败即抛（缓存缺失场景），预热失败不影响服务启动。
    """
    ok = get_reranker() is not None
    logger.info("重排模型预热完成" if ok else "重排模型预热跳过（不可用，问答将降级为仅 RRF 融合）")
    try:
        emb = get_embedder()
        logger.info("嵌入模型预热完成（dim=%s）", emb.dim)
    except EmbedderError as exc:
        logger.warning("嵌入模型预热失败（上传/问答将返回友好错误）：%s", exc)
    try:
        from .services.asr_service import get_asr
        ok_asr = get_asr() is not None
        logger.info("ASR 模型预热完成" if ok_asr else "ASR 模型预热跳过（语音输入将提示打字）")
    except Exception:
        logger.warning("ASR 预热异常（忽略，语音输入将降级）", exc_info=True)
    try:
        # 流式语音（自然对话）：VAD + 流式 ASR 合起来近 900MB，启动线程里顺序加载，
        # 加载完成前 /api/voice/capabilities 的 stream 为 false，前端不出自然对话入口
        from .services import asr_stream
        asr_stream.preload()
        logger.info("流式语音预热完成（VAD=%s, 流式ASR=%s）",
                    asr_stream.get_vad() is not None, asr_stream.get_stream_model() is not None)
    except Exception:
        logger.warning("流式语音预热异常（忽略，自然对话模式不可用）", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # 启动时建表（实训简化，不引入 Alembic）
    # 终审修复：启动即后台预热精排模型——否则首个 /ask 的请求线程承担 CrossEncoder
    # 懒加载（HF 不可达时下载重试可达数分钟，期间用户只见“思考中……”无反馈）。
    # daemon 线程不阻塞关停；get_reranker 失败缓存 False 哨兵，预热失败不影响服务。
    threading.Thread(target=_preheat_models, daemon=True, name="models-preheat").start()
    yield


app = FastAPI(title="edu-agent-platform", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(prep.router, prefix="/api/prep", tags=["prep"])
app.include_router(kb.router, prefix="/api/kb", tags=["kb"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(learn.router, prefix="/api/learn", tags=["learn"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
