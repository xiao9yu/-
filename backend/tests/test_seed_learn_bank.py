# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
"""Plan G 题库数据测试：每方向 72 题、题档分布、幂等落库、答案与选项结构、知识文档覆盖。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint, KpPrereq
from app.models.prep import Course, Lesson
from app.models.user import Role, User
from scripts.seed_learn_bank import (
    AI_EXERCISES, AI_KPS, AI_PREREQS, DS_EXERCISES, DS_KB_DOC, DS_KPS, DS_PREREQS,
    _seed_direction,
)
# 注意：ML_* 常量在 Task 3 才定义，本任务的 import 行不含 ML_*（Task 3 再扩展该行）。


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seedbank.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def course(db):
    teacher = User(username="t", hashed_password="x", role=Role.teacher)
    db.add(teacher)
    db.flush()
    c = Course(name="数据结构与算法", subject="数据结构与算法", owner_id=teacher.id)
    db.add(c)
    db.commit()
    return c


def _distribution(exercises):
    dist: dict[tuple, int] = {}
    for q in exercises:
        dist[(q["知识点"], q["难度"])] = dist.get((q["知识点"], q["难度"]), 0) + 1
    return dist


def test_ds_direction_72_questions_distribution():
    """DS 方向：12 知识点 × 易2/中2/难2 = 72 题。"""
    assert len(DS_EXERCISES) == 72
    assert {k for k, _ in DS_KPS} == {q["知识点"] for q in DS_EXERCISES}
    dist = _distribution(DS_EXERCISES)
    assert all(count == 2 for count in dist.values())
    assert len(dist) == 36  # 12 知识点 × 3 难度


def test_ds_questions_wellformed():
    """每题：4 个带字母前缀的选项、答案在 A~D、题干方向内唯一、解析非空。"""
    stems = [q["题干"] for q in DS_EXERCISES]
    assert len(stems) == len(set(stems))
    for q in DS_EXERCISES:
        assert len(q["选项"]) == 4
        assert all(o[:2] in {f"{c}." for c in "ABCD"} for o in q["选项"])
        assert q["答案"] in "ABCD"
        assert q["解析"].strip() and q["难度"] in ("易", "中", "难")


def test_seed_direction_idempotent(db, course):
    info = _seed_direction(db, course, DS_KPS, DS_PREREQS, DS_EXERCISES,
                           "数据结构与算法演示习题")
    assert info["exercises"] == 72
    assert db.query(KnowledgePoint).filter(
        KnowledgePoint.course_id == course.id).count() == 12
    assert db.query(KpPrereq).count() == 12
    lesson = db.query(Lesson).filter(Lesson.course_id == course.id).first()
    assert lesson is not None and len(lesson.content_json["习题"]) == 72
    _seed_direction(db, course, DS_KPS, DS_PREREQS, DS_EXERCISES,
                    "数据结构与算法演示习题")
    assert db.query(KnowledgePoint).count() == 12   # 不重复建知识点
    assert db.query(KpPrereq).count() == 12         # 不重复建边
    assert db.query(Lesson).count() == 1            # 不重复建 lesson


def test_ds_kb_doc_covers_all_kps():
    for name, _ in DS_KPS:
        assert name in DS_KB_DOC
