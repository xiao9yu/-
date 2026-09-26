# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""学生画像服务测试：诊断/导入初始化、时间衰减加权迭代、相似学生协同过滤。"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint, LearnEvent, ProfileKp, StudentProfile
from app.models.user import Role, User
from app.services import learn_profile

NAIVE_UTC = datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()  # 先释放会话连接，避免 drop_all 时 SQLite database is locked
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def _kp(db, name="梯度下降"):
    kp = KnowledgePoint(name=name)
    db.add(kp)
    db.commit()
    return kp


def test_decay_math(db, user):
    """2 天前的掌握度 100 → 100×0.95²=90.25。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    kp = _kp(db)
    profile = learn_profile.ensure_profile(user, db)
    db.add(ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=100.0,
                     difficulty="易", last_updated=now - timedelta(days=2)))
    # 补初始化事件（仅诊断/导入事件才算初始化，该事件不触碰掌握度）
    db.add(LearnEvent(user_id=user.id, event_type="diagnostic", kp_id=kp.id, delta=0.0))
    db.commit()
    data = learn_profile.get_profile(user, db)
    assert abs(data["kps"][0]["mastery"] - 90.25) < 0.01


def test_apply_event_first_time_and_clamp(db, user):
    kp = _kp(db)
    row = learn_profile.apply_event(user, kp, learn_profile.DELTA_PRACTICE_CORRECT, db,
                                    event_type="practice", correct=True)
    assert row.mastery == 10.0
    # 夹取上限 100
    row = learn_profile.apply_event(user, kp, 95.0, db, event_type="practice", correct=True)
    assert row.mastery == 100.0
    db.commit()
    assert db.query(LearnEvent).filter(LearnEvent.user_id == user.id).count() == 2


def test_apply_event_decay_then_add(db, user):
    """4 天前的 80 → 80×0.95⁴≈65.16，再 +10 → 75.16。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    kp = _kp(db)
    profile = learn_profile.ensure_profile(user, db)
    db.add(ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=80.0,
                     difficulty="易", last_updated=now - timedelta(days=4)))
    db.commit()
    row = learn_profile.apply_event(user, kp, 10.0, db, event_type="practice", correct=True)
    assert abs(row.mastery - 75.16) < 0.01


def test_init_from_diagnostic(db, user):
    answers = [
        {"knowledge_point": "梯度下降", "correct": True},
        {"knowledge_point": "梯度下降", "correct": False},
        {"knowledge_point": "线性回归", "correct": True},
    ]
    result = learn_profile.init_from_diagnostic(user, answers, db)
    assert result == {"initialized": True, "kp_count": 2}
    data = learn_profile.get_profile(user, db)
    by_name = {k["name"]: k["mastery"] for k in data["kps"]}
    assert by_name["梯度下降"] == 50.0 and by_name["线性回归"] == 100.0
    assert db.query(LearnEvent).filter(LearnEvent.event_type == "diagnostic").count() == 2


def test_init_from_import(db, user):
    result = learn_profile.init_from_import(user, ["梯度下降", "线性回归"], 80.0, db)
    assert result == {"initialized": True, "kp_count": 2}
    data = learn_profile.get_profile(user, db)
    assert all(k["mastery"] == 80.0 for k in data["kps"])
    assert db.query(LearnEvent).filter(LearnEvent.event_type == "import").count() == 2
    # 空知识点列表 → 业务异常
    from app.core.exceptions import BizError
    with pytest.raises(BizError):
        learn_profile.init_from_import(user, [], 80.0, db)


def test_record_ask_events(db, user):
    kp1 = _kp(db, "梯度下降")
    _kp(db, "卷积神经网络")
    n = learn_profile.record_ask_events(user, "梯度下降的学习率怎么调？", db)
    assert n == 1
    events = db.query(LearnEvent).filter(LearnEvent.event_type == "ask").all()
    assert len(events) == 1 and events[0].kp_id == kp1.id
    assert abs(events[0].delta - 2.0) < 0.001
    # 不命中任何知识点 → 不产生事件
    assert learn_profile.record_ask_events(user, "今天天气怎么样", db) == 0


def test_get_profile_uninitialized(db, user):
    assert learn_profile.get_profile(user, db) == \
        {"initialized": False, "kps": [], "created_at": None}


def test_get_profile_missing_kp_is_zero(db, user):
    kp = _kp(db, "梯度下降")
    profile = learn_profile.ensure_profile(user, db)
    # 补初始化事件（仅诊断/导入事件才算初始化）
    db.add(LearnEvent(user_id=user.id, event_type="import", kp_id=kp.id, delta=0.0))
    db.commit()
    data = learn_profile.get_profile(user, db)
    assert data["initialized"] is True
    assert data["kps"][0]["mastery"] == 0.0


def test_get_or_create_kp(db):
    kp = learn_profile.get_or_create_kp(db, "全新知识点")
    assert kp.id is not None and kp.description.startswith("（由学习行为自动登记）")
    assert learn_profile.get_or_create_kp(db, "全新知识点").id == kp.id


def test_similar_students_cosine_and_privacy(db, user):
    other = User(username="s2", hashed_password="x", role=Role.student, real_name="王同学")
    db.add(other)
    db.commit()
    kp_a = _kp(db, "梯度下降")
    kp_b = _kp(db, "线性回归")
    p1 = StudentProfile(user_id=user.id)
    p2 = StudentProfile(user_id=other.id)
    db.add_all([p1, p2])
    db.flush()
    now = NAIVE_UTC
    db.add_all([
        ProfileKp(profile_id=p1.id, kp_id=kp_a.id, mastery=100.0, last_updated=now),
        ProfileKp(profile_id=p2.id, kp_id=kp_a.id, mastery=100.0, last_updated=now),
        ProfileKp(profile_id=p2.id, kp_id=kp_b.id, mastery=80.0, last_updated=now),
    ])
    db.commit()
    results = learn_profile.similar_students(user, db)
    assert len(results) == 1
    r = results[0]
    assert r["user_id"] == other.id and r["real_name"] == "王同学"
    # 余弦相似度 10000/(100×128.06)≈0.78
    assert abs(r["similarity"] - 0.78) < 0.01
    # 仅返回"对方掌握而我未掌握"的知识点名（不泄露对方完整画像）
    assert r["strengths"] == ["线性回归"]
    assert "mastery" not in r


def test_initialized_requires_diagnostic_or_import(db, user):
    """仅有练习/提问事件产生的画像行不算初始化（未做诊断/导入仍引导诊断测试）。"""
    kp = _kp(db)
    learn_profile.apply_event(user, kp, learn_profile.DELTA_ASK, db, event_type="ask")
    db.commit()
    assert learn_profile.get_profile(user, db)["initialized"] is False
    learn_profile.init_from_import(user, [kp.name], 70.0, db)
    assert learn_profile.get_profile(user, db)["initialized"] is True


def test_profile_course_scoped_and_per_direction_init(db, user):
    """画像按课程过滤：方向 A 初始化不影响方向 B；kps 只含本课程知识点。"""
    from app.models.prep import Course
    ca = Course(name="课程A", subject="x", owner_id=1)
    cb = Course(name="课程B", subject="x", owner_id=1)
    db.add_all([ca, cb])
    db.flush()
    learn_profile.init_from_import(user, ["知识点A"], 60, db, course_id=ca.id)
    pa = learn_profile.get_profile(user, db, course_id=ca.id)
    pb = learn_profile.get_profile(user, db, course_id=cb.id)
    assert pa["initialized"] is True
    assert [k["name"] for k in pa["kps"]] == ["知识点A"]
    assert pb["initialized"] is False  # B 方向未初始化
