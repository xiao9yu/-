# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课数据模型测试：七张表的建表与基本 CRUD。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.file import FileRecord  # 注册 files 表（media_files 外键依赖）
from app.models.prep import Citation, Course, CourseFile, Exercise, Lesson, MediaFile, VersionSnapshot


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'prep.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def test_course_crud(db):
    course = Course(name="人工智能导论", subject="人工智能", description="导论课", owner_id=1)
    db.add(course)
    db.commit()
    got = db.get(Course, course.id)
    assert got.name == "人工智能导论"
    assert got.member_ids == []
    assert got.created_at is not None


def test_lesson_version_and_type(db):
    lesson = Lesson(course_id=1, title="第1课 教案", lesson_type="plan",
                    content_json={"标题": "测试"}, created_by=1)
    db.add(lesson)
    db.commit()
    got = db.get(Lesson, lesson.id)
    assert got.version == 1
    assert got.lesson_type == "plan"
    assert got.content_json["标题"] == "测试"


def test_exercise_standard_structure(db):
    """习题标准结构（中文键，工单19 复用）：题干/选项/答案/解析/知识点/难度。"""
    ex = Exercise(course_id=1, stem="梯度下降中控制步长的参数是",
                  options=["学习率", "批量大小", "迭代次数", "正则系数"],
                  answer="A", analysis="学习率控制步长", knowledge_point="梯度下降", difficulty="易")
    db.add(ex)
    db.commit()
    got = db.get(Exercise, ex.id)
    assert got.options[0] == "学习率"
    assert got.difficulty == "易"


def test_version_snapshot_and_citation(db):
    snap = VersionSnapshot(lesson_id=1, version=2, content_json={"标题": "旧版"}, created_by=1)
    cit = Citation(lesson_id=1, ref_no=1, source="教材.pdf", page=3, excerpt="梯度下降是……")
    db.add_all([snap, cit])
    db.commit()
    assert db.get(VersionSnapshot, snap.id).version == 2
    assert db.get(Citation, cit.id).ref_no == 1


def test_media_file_and_course_file(db):
    mf = MediaFile(lesson_id=1, file_id=10, position="body")
    cf = CourseFile(course_id=1, file_id=11)
    db.add_all([mf, cf])
    db.commit()
    assert db.get(MediaFile, mf.id).file_id == 10
    assert db.get(CourseFile, cf.id).file_id == 11
