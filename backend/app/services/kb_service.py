# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库服务：文档上传 → 多模态解析 → 分块 → 向量化入库 → 列表/删除。

集合约定：公共库 kb_public（admin 维护），私有库 kb_user_{user_id}（每用户一个）。
入库持久化：文档块落 kb_chunks 表，向量落向量库集合（Milvus/FAISS，Task 1 单例）。
"""
from fastapi import UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.file import FileRecord
from ..models.kb import KbChunk, KbDocument
from ..models.user import Role, User
from ..services.embeddings import EmbedderError, get_embedder
from ..services.file_service import delete_file, get_file_path, save_upload
from ..services.parser import parse_document
from ..services.vector_store import VectorStore, get_vector_store

PUBLIC_COLLECTION = "kb_public"


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
