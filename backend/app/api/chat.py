# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""会话接口：历史会话列表 / 单会话消息回放 / 删除会话。

消息回放带 citations 全量元数据，前端据此还原每轮的引用溯源——多轮场景下
"引用延续"指的是这件事：历史轮次的引用不会因为翻页或刷新而丢失。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..db import get_db
from ..models.user import User
from ..services import chat_service
from .deps import get_current_user

router = APIRouter()


@router.get("/sessions")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return chat_service.list_sessions(db, user)


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    session = chat_service.get_owned_session(db, user, session_id)
    if session is None:
        raise BizError(404, "会话不存在")
    return {"id": session.id, "title": session.title, "messages": chat_service.list_messages(db, session)}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if not chat_service.delete_session(db, user, session_id):
        raise BizError(404, "会话不存在")
    return {"ok": True}
