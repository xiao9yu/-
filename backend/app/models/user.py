# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""用户模型：四种角色覆盖工单17(教师)/18(师生)/19(学生)/20(就业指导+教师)。"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Role(str, enum.Enum):
    student = "student"      # 学生
    teacher = "teacher"      # 教师
    counselor = "counselor"  # 就业指导
    admin = "admin"          # 管理员


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
    real_name: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
