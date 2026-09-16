# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课模块数据模型：课程/教案课件/习题/版本快照/多媒体/引用/课程资源。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Course(Base):
    """课程：备课的组织单元；member_ids 存协作者（协同编辑 V1 简化）。"""
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(50), default="人工智能")   # 学科
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(Integer, index=True)            # 创建者
    member_ids: Mapped[list] = mapped_column(JSON, default=list)          # 协作者用户 id 列表
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Lesson(Base):
    """教案/课件大纲/习题集/月考试题：content_json 存结构化内容（键见各生成服务）。"""
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    lesson_type: Mapped[str] = mapped_column(String(20))  # plan|cw|exercises|exam
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Exercise(Base):
    """习题：标准结构（题干/选项/答案/解析/知识点/难度），工单 19 复用。"""
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    stem: Mapped[str] = mapped_column(Text)               # 题干
    options: Mapped[list] = mapped_column(JSON, default=list)  # 选项列表
    answer: Mapped[str] = mapped_column(String(200))      # 答案
    analysis: Mapped[str] = mapped_column(Text, default="")    # 解析
    knowledge_point: Mapped[str] = mapped_column(String(100), default="")  # 知识点
    difficulty: Mapped[str] = mapped_column(String(10), default="易")       # 易/中/难
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class VersionSnapshot(Base):
    """版本快照：每次保存/恢复时写入，支持历史回溯。"""
    __tablename__ = "version_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class MediaFile(Base):
    """教案/课件中插入的多媒体文件（关联底座 files 表）。"""
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))   # 底座 FileRecord
    position: Mapped[str] = mapped_column(String(50), default="body")  # 插入位置标记
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Citation(Base):
    """引用记录：资源检索后插入正文的引用标注。"""
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    ref_no: Mapped[int] = mapped_column(Integer)               # [N] 编号
    source: Mapped[str] = mapped_column(String(255))           # 来源文件名
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 页码（可空）
    excerpt: Mapped[str] = mapped_column(Text, default="")     # 原文摘录
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class CourseFile(Base):
    """课程级资源文件关联（资源检索的语料来源；设计文档表清单的合理扩展）。"""
    __tablename__ = "course_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
