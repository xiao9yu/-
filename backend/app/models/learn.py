# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习数据模型：知识点图谱/学生画像/学习事件/错题本。

设计要点（工单19）：
- 知识图谱：SQL 表存知识点与前置关系（本机未装 Neo4j，按工单16 退化方案），networkx 负责拓扑排序；
- 学生画像：profile 行 + 每知识点掌握度行（mastery 0~100，difficulty 为当前练习难度档）；
- 学习事件：画像迭代留痕（诊断/练习/提问/导入），时间衰减在服务层按 last_updated 计算；
- 错题本：答错登记 + AIGC 解析（status: pending|generated|failed）。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class KnowledgePoint(Base):
    """知识点节点。name 与工单17 试题的"知识点"字段对齐（画像/练习按名关联）。"""

    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class KpPrereq(Base):
    """知识点前置关系：kp_id 依赖 prereq_kp_id（先学 prereq 再学 kp）。"""

    __tablename__ = "kp_prereqs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    prereq_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)


class StudentProfile(Base):
    """学生画像头：一行即"已初始化"（无行 = 未做诊断测试/导入）。"""

    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ProfileKp(Base):
    """学生-知识点掌握度（0~100）与当前练习难度档（易/中/难）。"""

    __tablename__ = "profile_kps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[str] = mapped_column(String(10), default="易")
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class LearnEvent(Base):
    """学习行为事件（画像迭代留痕）。event_type: diagnostic|practice|ask|import。"""

    __tablename__ = "learn_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    delta: Mapped[float] = mapped_column(Float, default=0.0)   # 掌握度增量（正负）
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # practice 用
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class WrongQuestion(Base):
    """AIGC 错题本：答错登记 + DeepSeek 生成的解析/错误原因/变式题。"""

    __tablename__ = "wrong_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stem: Mapped[str] = mapped_column(Text)                    # 原题干
    options: Mapped[list] = mapped_column(JSON, default=list)
    user_answer: Mapped[str] = mapped_column(String(200))      # 学生错误答案
    correct_answer: Mapped[str] = mapped_column(String(200))
    knowledge_point: Mapped[str] = mapped_column(String(100), default="")
    difficulty: Mapped[str] = mapped_column(String(10), default="易")
    analysis: Mapped[str] = mapped_column(Text, default="")    # AIGC 解析
    error_reason: Mapped[str] = mapped_column(Text, default="")  # 错误原因（常见错误类型）
    variants: Mapped[list] = mapped_column(JSON, default=list)   # 变式题 [{题干,选项,答案,解析}]
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|generated|failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
