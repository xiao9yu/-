# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""会话数据模型：多轮对话会话（chat_sessions）与消息（chat_messages）。

设计取舍：会话与消息落库而非仅存前端内存——WS 语音链路的重连（前端最多重试 3 次）
与"刷新页面后继续上次对话"都要求上下文在服务端，且引用溯源要能随历史轮次回放。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ChatSession(Base):
    """一次连续对话。title 取首问前 30 字，便于前端列出历史会话。"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)   # 仅本人可见
    title: Mapped[str] = mapped_column(String(60), default="")
    turns: Mapped[int] = mapped_column(Integer, default=0)      # 已完成问答轮数
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ChatMessage(Base):
    """会话内一条消息。role: user（提问）| assistant（朵娅回答）。

    citations 存该轮引用的完整元数据（含全文与 chunk_id），历史回放时不重跑检索
    也能还原"引用溯源"——这正是"引用延续"要保住的东西。
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
