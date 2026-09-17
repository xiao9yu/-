# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库接口：文档上传/列表/删除、知识块图片、SSE 流式问答。"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..core.exceptions import BizError
from ..db import get_db
from ..models.kb import KbChunk, KbDocument
from ..models.user import Role, User
from ..services import kb_service
from ..services.embeddings import EmbedderError
from ..services.rerank import get_reranker
from .deps import get_current_user

router = APIRouter()


class AskIn(BaseModel):
    question: str


@router.post("/documents")
def upload_document(file: UploadFile = File(...), scope: str = Form("private"),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """上传文档入库：公共库仅 admin（kb_service 校验）；bge-m3 不可用转 502 友好提示。"""
    try:
        doc = kb_service.add_document(file, scope, user, settings.upload_dir, db)
    except EmbedderError as exc:
        raise BizError(502, str(exc)) from exc
    return {"id": doc.id, "title": doc.title, "scope": doc.scope,
            "status": doc.status, "chunk_count": doc.chunk_count}


@router.get("/documents")
def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        {"id": d.id, "title": d.title, "scope": d.scope, "owner_id": d.owner_id,
         "status": d.status, "error": d.error, "chunk_count": d.chunk_count,
         "created_at": d.created_at.isoformat()}
        for d in kb_service.list_documents(user, db)
    ]


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb_service.delete_document(doc_id, user, settings.upload_dir, db)
    return {"ok": True}


@router.get("/chunks/{chunk_id}/image")
def chunk_image(chunk_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """知识块原图：公共库 chunk 全员可看，私有库仅 owner/admin（前端 fetch blob 展示）。"""
    chunk = db.get(KbChunk, chunk_id)
    if chunk is None:
        raise BizError(404, "知识块不存在")
    doc = db.get(KbDocument, chunk.document_id)
    if doc is None:
        raise BizError(404, "文档不存在")
    if doc.scope == "private" and doc.owner_id != user.id and user.role != Role.admin:
        raise BizError(403, "无权访问该图片")
    image_path = (chunk.meta or {}).get("image_path")
    if not image_path:
        raise BizError(404, "该知识块无图片")
    path = Path(image_path)
    if not path.exists():
        raise BizError(404, "图片文件缺失")
    return FileResponse(path)


@router.post("/ask")
def ask(data: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """流式问答（SSE）：citations → delta* → done；失败发 error 事件。"""
    if not data.question.strip():
        raise BizError(400, "问题不能为空")
    return StreamingResponse(
        kb_service.ask_stream(data.question, user, db, reranker=get_reranker()),
        media_type="text/event-stream",
    )
