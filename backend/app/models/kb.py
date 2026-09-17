# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库数据模型：文档登记（kb_documents）与多模态知识块（kb_chunks）。

入库链路：文件底座落盘（files 表）→ 文档登记 → 解析分块 → 向量化入集合
（kb_public / kb_user_{owner_id}）→ 块落表。检索时按文档状态过滤，从块表回查语料。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class KbDocument(Base):
    """知识库文档登记。scope: public(公共库，admin 维护) | private(个人私有库)。"""

    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))              # 原始文件名
    file_id: Mapped[int] = mapped_column(Integer, index=True)    # FileRecord.id（底座文件）
    scope: Mapped[str] = mapped_column(String(10), default="private")
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(10), default="ready")  # ready | failed
    error: Mapped[str] = mapped_column(String(500), default="")       # 向量化失败原因
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class KbChunk(Base):
    """多模态知识块。kind: text(文本) | table(表格 markdown) | image(图片 OCR + 原图路径)。"""

    __tablename__ = "kb_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4().hex，与向量 id 一致
    document_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(255), default="")   # 原始文件名（引用标注）
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)         # image_path / file_id / sheet 名等
