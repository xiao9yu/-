# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习数据模型测试：知识点图谱/画像/学习事件/错题本。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import (
    KnowledgePoint, KpPrereq, LearnEvent, ProfileKp, StudentProfile, WrongQuestion,
)
from app.models.user import Role, User


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'learn.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def test_knowledge_point_and_prereq(db):
    kp1 = KnowledgePoint(name="梯度下降", description="最优化算法")
    kp2 = KnowledgePoint(name="线性回归")
    db.add_all([kp1, kp2])
    db.commit()
    db.add(KpPrereq(kp_id=kp2.id, prereq_kp_id=kp1.id))
    db.commit()
    edge = db.query(KpPrereq).first()
    assert edge.kp_id == kp2.id and edge.prereq_kp_id == kp1.id


def test_student_profile_kp_defaults(db, user):
    profile = StudentProfile(user_id=user.id)
    db.add(profile)
    db.flush()
    kp = KnowledgePoint(name="梯度下降")
    db.add(kp)
    db.flush()
    db.add(ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=50.0, difficulty="易"))
    db.commit()
    got = db.query(ProfileKp).first()
    assert got.mastery == 50.0
    assert got.difficulty == "易"
    assert got.last_updated is not None
    p = db.query(StudentProfile).first()
    assert p.created_at is not None and p.updated_at is not None


def test_learn_event_types(db, user):
    kp = KnowledgePoint(name="梯度下降")
    db.add(kp)
    db.flush()
    db.add(LearnEvent(user_id=user.id, event_type="practice", kp_id=kp.id,
                      delta=10.0, correct=True, detail="练习"))
    db.add(LearnEvent(user_id=user.id, event_type="ask", kp_id=kp.id,
                      delta=2.0, correct=None, detail="提问"))
    db.commit()
    assert db.query(LearnEvent).filter(LearnEvent.correct.is_(True)).count() == 1
    assert db.query(LearnEvent).filter(LearnEvent.correct.is_(None)).count() == 1


def test_wrong_question_defaults_and_json(db, user):
    wq = WrongQuestion(user_id=user.id, stem="学习率过大会？", options=["A.收敛慢", "B.震荡"],
                       user_answer="A", correct_answer="B", knowledge_point="梯度下降",
                       difficulty="中")
    db.add(wq)
    db.commit()
    got = db.get(WrongQuestion, wq.id)
    assert got.status == "pending"
    assert got.analysis == ""
    assert got.variants == []
    got.variants = [{"题干": "变式1", "选项": ["A", "B"], "答案": "A", "解析": ""}]
    db.commit()
    assert db.get(WrongQuestion, wq.id).variants[0]["题干"] == "变式1"
