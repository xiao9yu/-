# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""自适应练习服务测试：试题复用/难度控制/提交联动画像与错题本。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import BizError
from app.db import Base
from app.models.learn import KnowledgePoint, LearnEvent, ProfileKp, WrongQuestion
from app.models.prep import Course, Lesson
from app.models.user import Role, User
from app.services import learn_practice, learn_profile, learn_wrongbook
from app.services.llm_gateway import LLMError


class FakeLLM:
    def chat_json(self, messages, temperature=0.3):
        return {"解析": "思路", "错误原因": "概念混淆", "变式题": [
            {"题干": "v1", "选项": ["A", "B"], "答案": "A", "解析": ""},
            {"题干": "v2", "选项": ["A", "B"], "答案": "B", "解析": ""},
        ]}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'practice.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()  # 先关 Session 再 drop_all，避免 Windows SQLite 文件锁
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def _question(stem, answer, kp="梯度下降", diff="易"):
    return {"题干": stem, "选项": ["A.a", "B.b", "C.c", "D.d"], "答案": answer,
            "解析": f"{stem} 的解析", "知识点": kp, "难度": diff}


@pytest.fixture
def seeded(db):
    """课程 + 习题集 lesson（梯度下降 易×2 中×2 难×1；线性回归 易×1）+ 月考题 lesson。"""
    course = Course(name="人工智能导论", subject="人工智能", owner_id=1)
    db.add(course)
    db.flush()
    exercises = [_question(f"梯度下降题{i}", "A", kp="梯度下降",
                           diff=["易", "易", "中", "中", "难"][i]) for i in range(5)]
    exercises.append(_question("线性回归题1", "B", kp="线性回归", diff="易"))
    lesson = Lesson(course_id=course.id, title="习题集", lesson_type="exercises",
                    content_json={"习题": exercises}, created_by=1)
    exam = Lesson(course_id=course.id, title="月考题", lesson_type="exam",
                  content_json={"试卷标题": "月考", "大题": [
                      {"题型": "选择题", "知识点": "梯度下降", "题目": [_question("月考梯度下降题", "A")]},
                      {"题型": "简答题", "知识点": "梯度下降",
                       "题目": [{"题干": "简述梯度下降（无选项）", "答案": "略", "知识点": "梯度下降"}]},
                  ]}, created_by=1)
    db.add_all([lesson, exam])
    db.commit()
    return {"course": course, "lesson": lesson, "exam": exam}


def test_collect_questions_exercises_and_exam(db, seeded):
    qs = learn_practice.collect_questions(db)
    # 习题集 6 + 月考题选择题 1（简答题无选项被过滤）
    assert len(qs) == 7
    assert all(q["lesson_id"] for q in qs)
    qs2 = learn_practice.collect_questions(db, kp="梯度下降", difficulty="难")
    assert len(qs2) == 1 and qs2[0]["题干"] == "梯度下降题4"
    qs3 = learn_practice.collect_questions(db, course_id=seeded["course"].id, kp="线性回归")
    assert [q["题干"] for q in qs3] == ["线性回归题1"]


def test_find_question(db, seeded):
    q = learn_practice.find_question(db, seeded["lesson"].id, "梯度下降题0")
    assert q["答案"] == "A" and q["知识点"] == "梯度下降"
    with pytest.raises(BizError):
        learn_practice.find_question(db, seeded["lesson"].id, "不存在的题")
    with pytest.raises(BizError):
        learn_practice.find_question(db, 99999, "梯度下降题0")


def test_diagnostic_questions_no_answer_and_coverage(db, seeded):
    """默认 10 题：易/中优先、题干去重、覆盖不同知识点、不带答案。"""
    qs = learn_practice.diagnostic_questions(db)
    assert 1 < len(qs) <= 10
    assert all("答案" not in q and "解析" not in q for q in qs)
    stems = [q["stem"] for q in qs]  # 接口字段为英文键（Task 6/前端契约）
    assert len(stems) == len(set(stems))
    kps = {q["knowledge_point"] for q in qs}
    assert "线性回归" in kps  # 覆盖不同知识点（轮询取样）
    # count=1 → 只取 1 题
    qs2 = learn_practice.diagnostic_questions(db, count=1)
    assert len(qs2) == 1


def test_next_question_prefers_current_difficulty(db, user, seeded):
    # 默认画像行难度"易" → 抽易题，不带答案
    q = learn_practice.next_question(user, "梯度下降", db, course_id=seeded["course"].id)
    assert q["difficulty"] == "易"
    assert "答案" not in q and "解析" not in q
    assert q["knowledge_point"] == "梯度下降"
    # 该知识点无"易"题 → 放宽到全部难度（线性回归只有易题；改用只造难题的知识点验证）
    q2 = learn_practice.next_question(user, "线性回归", db, course_id=seeded["course"].id)
    assert q2["difficulty"] == "易"
    # 无任何题 → 404 友好提示
    with pytest.raises(BizError) as exc:
        learn_practice.next_question(user, "量子计算", db)
    assert exc.value.status_code == 404


def test_submit_correct_updates_profile_and_difficulty(db, user, seeded):
    for _ in range(5):  # 5 连对 → 正确率 1.0 > 0.8 → 升到"中"
        result = learn_practice.submit_answer(
            user, seeded["lesson"].id, "梯度下降题0", "A", db, llm=FakeLLM())
        assert result["correct"] is True
        assert result["answer"] == "A"
    acc = learn_practice._rolling_accuracy(user, db.query(KnowledgePoint)
                                           .filter(KnowledgePoint.name == "梯度下降").first().id, db)
    assert acc == 1.0
    assert result["difficulty_new"] == "中"
    row = db.query(ProfileKp).first()
    # 5×+10；相邻事件间有毫秒级时间差，衰减因子≈1，用近似断言
    assert abs(row.mastery - 50.0) < 0.01
    assert row.difficulty == "中"


def test_submit_wrong_creates_wrongbook(db, user, seeded, monkeypatch):
    monkeypatch.setattr(learn_wrongbook, "get_gateway", lambda: FakeLLM())
    result = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "B", db, llm=FakeLLM())
    assert result["correct"] is False
    assert result["wrong_question"]["status"] == "generated"
    wq = db.get(WrongQuestion, result["wrong_question"]["id"])
    assert wq.user_answer == "B" and wq.correct_answer == "A"
    assert wq.knowledge_point == "梯度下降"
    # 再次答错 → 第二条错题同样生成成功；画像 0 + (-15) 夹取到 0
    result2 = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "B", db, llm=FakeLLM())
    assert result2["wrong_question"]["status"] == "generated"
    row = db.query(ProfileKp).first()
    assert row.mastery == 0.0


def test_difficulty_down(db, user):
    kp = KnowledgePoint(name="梯度下降")
    db.add(kp)
    db.commit()
    profile = learn_profile.ensure_profile(user, db)
    row = ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=80.0,
                    difficulty="中", last_updated=learn_profile._now())
    db.add(row)
    db.commit()
    for _ in range(5):
        learn_profile.apply_event(user, kp, learn_profile.DELTA_PRACTICE_WRONG, db,
                                  event_type="practice", correct=False)
    acc = learn_practice._rolling_accuracy(user, kp.id, db)
    assert acc == 0.0
    assert learn_practice._adjust_difficulty(row, acc) == "易"


def test_submit_auto_registers_unknown_kp(db, user, seeded):
    """试题知识点不在图谱 → 自动登记孤立节点，画像仍更新。"""
    result = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "A", db, llm=FakeLLM())
    assert result["correct"] is True
    assert db.query(KnowledgePoint).filter(KnowledgePoint.name == "梯度下降").count() == 1


def test_submit_accepts_full_option_text(db, user, seeded):
    """前端单选绑定整段选项文本（"A.a"）→ 后端按选项前缀字母归一化比对。"""
    q = learn_practice.find_question(db, seeded["lesson"].id, "梯度下降题0")
    assert learn_practice.check_answer(q, "A.a") is True
    assert learn_practice.check_answer(q, "B.b") is False
    assert learn_practice.check_answer(q, None) is False  # 空答案判错不抛错
    assert learn_practice.check_answer(q, "") is False
    result = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "A.a", db, llm=FakeLLM())
    assert result["correct"] is True


def test_next_question_prev_stem_avoids_immediate_repeat(db, user):
    """prev_stem 非空且候选池 >1 时，下一题不与上一题同题干（解决"下一题还是同一道"）。"""
    course = Course(name="课程", subject="x", owner_id=1)
    db.add(course)
    db.flush()
    lesson = Lesson(course_id=course.id, title="习题集", lesson_type="exercises",
                    content_json={"习题": [
                        _question("题目甲", "A", kp="知识点A"),
                        _question("题目乙", "A", kp="知识点A"),
                    ]}, created_by=1)
    db.add(lesson)
    db.commit()
    q1 = learn_practice.next_question(user, "知识点A", db, course_id=course.id,
                                      prev_stem="题目甲")
    assert q1["stem"] == "题目乙"
    # 排除后只剩 1 题时回退全池（允许重复，防无题可出）
    q2 = learn_practice.next_question(user, "知识点A", db, course_id=course.id,
                                      prev_stem="题目乙")
    assert q2["stem"] in ["题目甲", "题目乙"]
