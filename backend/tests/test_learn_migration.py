# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
"""Plan G 知识点课程隔离与旧库迁移测试：同名知识点分课程共存、旧库加列回填、唯一约束重建。"""
import sqlalchemy as sa
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint
from app.models.prep import Course
from app.models.user import Role, User


@pytest.fixture
def db(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


def test_kp_same_name_allowed_in_different_courses(db):
    """同一知识点名在不同课程下互不冲突；同课程同名违反唯一约束。"""
    teacher = User(username="t", hashed_password="x", role=Role.teacher)
    db.add(teacher)
    db.flush()
    c1 = Course(name="课程甲", subject="x", owner_id=teacher.id)
    c2 = Course(name="课程乙", subject="x", owner_id=teacher.id)
    db.add_all([c1, c2])
    db.flush()
    db.add(KnowledgePoint(name="决策树", course_id=c1.id))
    db.add(KnowledgePoint(name="决策树", course_id=c2.id))
    db.commit()  # 不同课程同名合法
    db.add(KnowledgePoint(name="决策树", course_id=c1.id))
    with pytest.raises(sa.exc.IntegrityError):  # 同课程同名撞唯一约束
        db.commit()


def _legacy_db(tmp_path):
    """构造 Plan G 之前的旧库：knowledge_points 无 course_id 列、name 全局唯一索引；
    wrong_questions 无 course_id 列（错题只存知识点名字符串）。"""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE courses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "name VARCHAR(100))"))
        conn.execute(text("INSERT INTO courses (name) VALUES ('人工智能导论')"))
        conn.execute(text("CREATE TABLE knowledge_points ("
                          "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "name VARCHAR(100), description TEXT, created_at DATETIME)"))
        conn.execute(text("CREATE UNIQUE INDEX ix_knowledge_points_name "
                          "ON knowledge_points (name)"))
        conn.execute(text("INSERT INTO knowledge_points (name) VALUES ('梯度下降')"))
        conn.execute(text("CREATE TABLE wrong_questions ("
                          "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "user_id INTEGER, knowledge_point VARCHAR(100))"))
        conn.execute(text("INSERT INTO wrong_questions (user_id, knowledge_point) "
                          "VALUES (1, '决策树')"))
    return engine


def test_migrate_learn_schema_backfills_and_reindexes(tmp_path):
    """旧库 → 迁移后：加列、回填 AI 课程、移除旧 name 唯一索引、重建 (course_id, name) 唯一索引；
    wrong_questions 同样加 course_id 列并回填 AI 课程；幂等。"""
    from scripts import seed_demo_data
    engine = _legacy_db(tmp_path)
    Session = sessionmaker(bind=engine)
    db = Session()
    seed_demo_data.migrate_learn_schema(db)
    cols = {c["name"] for c in sa.inspect(engine).get_columns("knowledge_points")}
    assert "course_id" in cols
    row = db.execute(text("SELECT kp.name, c.name FROM knowledge_points kp "
                          "JOIN courses c ON kp.course_id = c.id")).fetchone()
    assert tuple(row) == ("梯度下降", "人工智能导论")  # 旧知识点回填 AI 课程
    idx = {r[1]: bool(r[2]) for r in db.execute(text("PRAGMA index_list(knowledge_points)"))}
    assert idx.get("uq_kp_course_name") is True        # 新唯一索引存在
    assert "ix_knowledge_points_name" not in idx       # 旧 name 唯一索引已移除
    # 错题本课程隔离迁移：加列 + NULL 存量行回填「人工智能导论」
    cols_wq = {c["name"] for c in sa.inspect(engine).get_columns("wrong_questions")}
    assert "course_id" in cols_wq
    wq = db.execute(text("SELECT wq.knowledge_point, c.name FROM wrong_questions wq "
                         "JOIN courses c ON wq.course_id = c.id")).fetchone()
    assert tuple(wq) == ("决策树", "人工智能导论")     # 旧错题回填 AI 课程
    seed_demo_data.migrate_learn_schema(db)            # 幂等：再跑一遍不报错
