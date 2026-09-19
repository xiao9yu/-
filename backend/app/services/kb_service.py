# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库服务：文档上传 → 多模态解析 → 分块 → 向量化入库 → 列表/删除。

集合约定：公共库 kb_public（admin 维护），私有库 kb_user_{user_id}（每用户一个）。
入库持久化：文档块落 kb_chunks 表，向量落向量库集合（Milvus/FAISS，Task 1 单例）。
"""
import json
import logging
from typing import Any, Iterator

from fastapi import UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.file import FileRecord
from ..models.kb import KbChunk, KbDocument
from ..models.user import Role, User
from ..services.embeddings import EmbedderError, get_embedder
from ..services.file_service import delete_file, get_file_path, save_upload
from ..services.llm_gateway import LLMError, get_gateway
from ..services.parser import parse_document
from ..services.parser.chunk import Chunk
from ..services.rag import KBCollection, hybrid_retrieve
from ..services.rag_ask import _select_hits, build_answer_prompt
from ..services.vector_store import VectorStore, get_vector_store
from . import learn_profile

PUBLIC_COLLECTION = "kb_public"

logger = logging.getLogger("kb_service")


def private_collection(user_id: int) -> str:
    """私有库集合名（每用户一个）。"""
    return f"kb_user_{user_id}"


def _collection(doc: KbDocument) -> str:
    return PUBLIC_COLLECTION if doc.scope == "public" else private_collection(doc.owner_id)


def add_document(file: UploadFile, scope: str, user: User, upload_dir, db: Session,
                 *, vector_store: VectorStore | None = None, embedder=None) -> KbDocument:
    """上传文档入库：底座落盘 → 登记 → 解析分块 → 向量化入集合 → 块落表。

    解析为空（含 .doc/.ppt/.xls 二进制老格式）拒绝上传并回滚；
    向量化失败（bge-m3 不可用）保留文档记录 status=failed，EmbedderError 上抛由路由转 502；
    其他未预期异常（向量库故障/解析崩溃）同样记 failed 后上抛（不产生"ready 但 0 块"幻影文档）。
    """
    if scope not in ("public", "private"):
        raise BizError(400, "scope 仅支持 public（公共库）或 private（私有库）")
    if scope == "public" and user.role != Role.admin:
        raise BizError(403, "仅管理员可向公共库上传文档")
    record = save_upload(file, owner_id=user.id, upload_dir=upload_dir, db=db)
    doc = KbDocument(title=record.filename, file_id=record.id, scope=scope, owner_id=user.id)
    # 先记 failed 再提交：索引成功后 _index_document 才置 ready，防止中途异常/崩溃留下幻影 ready 文档
    doc.status = "failed"
    db.add(doc)
    db.commit()
    db.refresh(doc)
    try:
        _index_document(doc, record, upload_dir, db, vector_store=vector_store, embedder=embedder)
    except BizError:
        # 解析为空：整体回滚（文档记录 + 底座文件 + 磁盘）
        db.delete(doc)
        db.commit()
        delete_file(record.id, upload_dir, db)
        raise
    except EmbedderError as exc:
        doc.status = "failed"
        doc.error = str(exc)
        db.commit()
        raise
    except Exception as exc:
        # 其他异常（向量库故障/解析崩溃/提交失败）记 failed 后上抛（复审修复：幻影 ready 文档）
        doc.status = "failed"
        doc.error = str(exc)
        db.commit()
        raise
    return doc


def _index_document(doc: KbDocument, record: FileRecord, upload_dir, db: Session,
                    *, vector_store=None, embedder=None) -> None:
    path = get_file_path(record, upload_dir)
    chunks = [c for c in parse_document(path) if c.text.strip()]
    # 空文本块（含 OCR 空图片块）不参与向量化：零向量 normalize 会产 NaN 污染索引
    if not chunks:
        raise BizError(400, "文档解析结果为空：请确认内容为可提取文本，"
                            "或将 .doc/.ppt/.xls 转换为 .docx/.pptx/.xlsx 后上传")
    for c in chunks:
        c.source = record.filename            # 引用标注用原始文件名
        c.meta["file_id"] = record.id
    emb = embedder or get_embedder()
    vs = vector_store or get_vector_store()
    col = _collection(doc)
    vs.create_collection(col, dim=emb.dim)
    vs.upsert(
        col,
        ids=[c.id for c in chunks],
        vectors=emb.embed_texts([c.text for c in chunks]),
        metadatas=[{"chunk_id": c.id, "source": c.source, "page": c.page,
                    "file_id": record.id, "scope": doc.scope} for c in chunks],
    )
    db.add_all([KbChunk(id=c.id, document_id=doc.id, kind=c.kind, text=c.text,
                        source=c.source, page=c.page, meta=c.meta) for c in chunks])
    doc.chunk_count = len(chunks)
    doc.status = "ready"
    db.commit()


def list_documents(user: User, db: Session) -> list[KbDocument]:
    """文档列表：本人私有库 + 全部公共库（他人私有不可见）。"""
    return (db.query(KbDocument)
            .filter(or_(KbDocument.scope == "public", KbDocument.owner_id == user.id))
            .order_by(KbDocument.created_at.desc())
            .all())


def delete_document(doc_id: int, user: User, upload_dir, db: Session,
                    *, vector_store=None) -> None:
    """删除文档：仅 owner 或 admin；公共库文档仅 admin。同步清理向量、块、底座文件与磁盘。"""
    doc = db.get(KbDocument, doc_id)
    if doc is None:
        raise BizError(404, "文档不存在")
    if doc.scope == "public":
        if user.role != Role.admin:
            raise BizError(403, "公共库文档仅管理员可删除")
    elif doc.owner_id != user.id and user.role != Role.admin:
        raise BizError(403, "无权删除他人私有库文档")
    chunks = db.query(KbChunk).filter(KbChunk.document_id == doc_id).all()
    vs = vector_store or get_vector_store()
    vs.delete(_collection(doc), [c.id for c in chunks])
    for c in chunks:
        db.delete(c)
    file_id = doc.file_id
    db.delete(doc)
    db.commit()
    delete_file(file_id, upload_dir, db)


def answer_events(question: str, user: User, db: Session, *,
                  vector_store=None, embedder=None, reranker=None, gateway=None) -> Iterator[tuple[str, Any]]:
    """问答事件流（(事件名, 数据) 元组）：citations → delta* → done；失败发 error。

    ask_stream 的 SSE 字符串仅是它的薄包装；WS 语音链路（api/voice.py）直接消费本生成器。
    """
    try:
        # 经本模块 get_embedder 解析嵌入模型后显式传入 hybrid_retrieve：
        # 避免 rag 模块内部再走真实 bge-m3（测试 monkeypatch 本模块 get_embedder 即可覆盖全链路）
        emb = embedder or get_embedder()
        hits = hybrid_retrieve(question, _load_collections(user, db), top_k=5,
                               vector_store=vector_store, embedder=emb, rerank=reranker)
        selected = _select_hits(hits, 4000)
        citations = [
            {
                "ref_no": i,
                "source": h.chunk.source,
                "page": h.chunk.page,
                "kind": h.chunk.kind,
                "excerpt": h.chunk.text[:200],
                "text": h.chunk.text,                       # 全文（前端"展开原文"）
                "image_path": h.chunk.meta.get("image_path"),
                "chunk_id": h.chunk.id,
            }
            for i, h in selected
        ]
        yield ("citations", citations)
        gw = gateway or get_gateway()
        for piece in gw.chat_stream(build_answer_prompt(question, hits)):
            yield ("delta", {"text": piece})
        # 工单19 画像迭代联动：学生提问命中知识点 → 记低权重事件（失败不影响问答流）
        if user.role == Role.student:
            try:
                learn_profile.record_ask_events(user, question, db)
            except Exception:
                logger.exception("画像事件记录失败（问答不受影响）")
        yield ("done", {})
    except EmbedderError as exc:
        yield ("error", {"message": str(exc)})
    except LLMError as exc:
        yield ("error", {"message": str(exc)})
    except BizError as exc:
        yield ("error", {"message": exc.message})
    except Exception:
        # 兜底：向量库检索故障/精排期异常等未预期错误也按协议发 error，不截断流（复审 Important）
        logger.exception("知识库问答流异常")
        yield ("error", {"message": "问答服务异常，请稍后重试"})


def ask_stream(question: str, user: User, db: Session, *,
               vector_store=None, embedder=None, reranker=None, gateway=None) -> Iterator[str]:
    """流式问答（SSE 生成器）：answer_events 的 SSE 字符串包装（既有前端/测试契约不变）。"""

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    for event, data in answer_events(question, user, db,
                                     vector_store=vector_store, embedder=embedder,
                                     reranker=reranker, gateway=gateway):
        yield sse(event, data)


def _load_collections(user: User, db: Session) -> list[KBCollection]:
    """检索语料：公共库全部 + 本人私有库（仅 ready 文档，按集合名组装）。"""
    def rows(cond):
        return (db.query(KbChunk).join(KbDocument, KbChunk.document_id == KbDocument.id)
                .filter(cond, KbDocument.status == "ready").all())

    def to_col(name, chunk_rows):
        chunks = [Chunk(text=r.text, kind=r.kind, source=r.source, id=r.id,
                        page=r.page, meta=dict(r.meta or {})) for r in chunk_rows]
        return KBCollection(name=name, chunks=chunks)

    cols = []
    public_rows = rows(KbDocument.scope == "public")
    if public_rows:
        cols.append(to_col(PUBLIC_COLLECTION, public_rows))
    private_rows = rows(and_(KbDocument.scope == "private", KbDocument.owner_id == user.id))
    if private_rows:
        cols.append(to_col(private_collection(user.id), private_rows))
    return cols
