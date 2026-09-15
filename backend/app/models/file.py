# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文件记录：所有上传的文档/图片/音频统一登记。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))     # 原始文件名
    stored_name: Mapped[str] = mapped_column(String(100))  # 磁盘名（uuid.后缀）
    ext: Mapped[str] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
