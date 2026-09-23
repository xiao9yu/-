# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习 API 测试：权限/诊断/导入/路径/任务/相似学生/练习/错题本/助教联动。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.db import Base
from app.main import app
from app.models.learn import KnowledgePoint, LearnEvent
from app.models.prep import Course, Lesson
from app.models.user import Role, User
from app.services import kb_service, learn_wrongbook


class FakeWrongbookLLM:
    def chat_json(self, messages, temperature=0.3):
        return {"解析": "解题思路", "错误原因": "概念混淆", "变式题": [
            {"题干": "变式1", "选项": ["A.a", "B.b"], "答案": "B", "解析": "略"},
            {"题干": "变式2", "选项": ["A.a", "B.b"], "答案": "A", "解析": "略"},
        ]}


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


class FakeStore:
    def search(self, name, query_vector, top_k, filter_dict=None):
        return []


class FakeAskGateway:
    def chat_stream(self, messages, temperature=0.7):
        yield "助教回答片段"


def _question(stem, answer, kp="梯度下降", diff="易"):
    return {"题干": stem, "选项": ["A.a", "B.b", "C.c", "D.d"], "答案": answer,
            "解析": f"{stem} 的解析", "知识点": kp, "难度": diff}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时 DB + 用户（student/teacher）+ 课程与习题集 + 假错题 LLM。"""
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    monkeypatch.setattr(learn_wrongbook, "get_gateway", lambda: FakeWrongbookLLM())
    from fastapi.testclient import TestClient
    client = TestClient(app)

    from app.core.security import create_access_token, hash_password
    s = Session()
    headers = {}
    for name, role in [("teacher", Role.teacher), ("student", Role.student),
                       ("student2", Role.student)]:
        u = User(username=name, hashed_password=hash_password("p"), role=role,
                 real_name=name)
        s.add(u)
        s.commit()
        s.refresh(u)
        headers[name] = {"Authorization": f"Bearer {create_access_token(u.id, u.role.value)}"}
    teacher = s.query(User).filter(User.username == "teacher").first()
    course = Course(name="人工智能导论", subject="人工智能", owner_id=teacher.id)
    s.add(course)
    s.commit()
    qs = []
    for i in range(8):
        qs.append(_question(f"诊断梯度下降题{i}", "A",
                            kp="梯度下降" if i % 2 == 0 else "线性回归", diff="易"))
    s.add(Lesson(course_id=course.id, title="诊断习题集", lesson_type="exercises",
                 content_json={"习题": qs}, created_by=teacher.id))
    s.commit()
    yield client, headers, tmp_path, Session, course
    app.dependency_overrides.clear()


def test_learn_routes_require_student(env):
    client, headers, *_ = env
    for path in ["/api/learn/profile", "/api/learn/path", "/api/learn/wrongbook"]:
        resp = client.get(path, headers=headers["teacher"])
        assert resp.status_code == 403
        assert "权限不足" in resp.json()["detail"]
    resp = client.get("/api/learn/profile")
    assert resp.status_code == 401


def test_profile_uninitialized_then_diagnostic_flow(env):
    client, headers, *_ = env
    resp = client.get("/api/learn/profile", headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json()["initialized"] is False
    # 获取诊断题：不带答案
    resp = client.get("/api/learn/diagnostic", headers=headers["student"])
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    assert len(questions) == 8
    assert all("答案" not in q and "解析" not in q for q in questions)
    # 全部作答 A → 全对
    answers = [{"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "A"}
               for q in questions]
    resp = client.post("/api/learn/diagnostic", json={"answers": answers},
                       headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json()["initialized"] is True
    profile = client.get("/api/learn/profile", headers=headers["student"]).json()
    by_name = {k["name"]: k["mastery"] for k in profile["kps"]}
    assert by_name["梯度下降"] == 100.0 and by_name["线性回归"] == 100.0
    # 全部掌握 → 路径为空
    resp = client.get("/api/learn/path", headers=headers["student"])
    assert resp.json()["path"] == []
    assert resp.json()["mastered"] == 2


def test_diagnostic_partial_and_path_tasks(env):
    client, headers, tmp_path, Session, course = env
    questions = client.get("/api/learn/diagnostic", headers=headers["student"]).json()["questions"]
    # 梯度下降题答错、线性回归题答对
    answers = [{"lesson_id": q["lesson_id"], "stem": q["stem"],
                "answer": "A" if q["knowledge_point"] == "线性回归" else "B"}
               for q in questions]
    resp = client.post("/api/learn/diagnostic", json={"answers": answers},
                       headers=headers["student"])
    assert resp.status_code == 200
    path = client.get("/api/learn/path", headers=headers["student"]).json()
    assert [p["name"] for p in path["path"]] == ["梯度下降"]
    assert "可直接学习" in path["path"][0]["why"]
    tasks = client.get("/api/learn/tasks", headers=headers["student"]).json()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "梯度下降" and tasks[0]["question"]["stem"]
    # 答题与题库不匹配 → 400
    bad = client.post("/api/learn/diagnostic",
                      json={"answers": [{"lesson_id": 1, "stem": "不存在", "answer": "A"}]},
                      headers=headers["student"])
    assert bad.status_code == 400
    # 畸形条目（缺 lesson_id/stem）→ 400 而非 500（终审修复：KeyError 兜底）
    bad = client.post("/api/learn/diagnostic",
                      json={"answers": [{"answer": "A"}]},
                      headers=headers["student"])
    assert bad.status_code == 400


def test_import_flow(env):
    client, headers, tmp_path, Session, course = env
    resp = client.post("/api/learn/import", json={"course_id": course.id, "score": 75},
                       headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json() == {"initialized": True, "kp_count": 2}
    profile = client.get("/api/learn/profile", headers=headers["student"]).json()
    assert all(k["mastery"] == 75.0 for k in profile["kps"])
    assert client.post("/api/learn/import", json={"course_id": course.id, "score": 150},
                       headers=headers["student"]).status_code == 400
    assert client.post("/api/learn/import", json={"course_id": 99999, "score": 80},
                       headers=headers["student"]).status_code == 400


def test_practice_flow(env):
    client, headers, *_ = env
    resp = client.get("/api/learn/practice", params={"kp": "梯度下降"},
                      headers=headers["student"])
    assert resp.status_code == 200
    q = resp.json()
    assert "答案" not in q and q["difficulty"] == "易"
    # 答对
    resp = client.post("/api/learn/practice/submit",
                       json={"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "A"},
                       headers=headers["student"])
    data = resp.json()
    assert data["correct"] is True and data["analysis"]
    # 答错 → 错题入册（假 LLM 生成成功）
    resp = client.post("/api/learn/practice/submit",
                       json={"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "B"},
                       headers=headers["student"])
    data = resp.json()
    assert data["correct"] is False
    assert data["wrong_question"]["status"] == "generated"
    assert data["difficulty_new"] == "易"  # 样本不足不调整
    # 错题本列表 + 重新生成
    resp = client.get("/api/learn/wrongbook", headers=headers["student"])
    assert len(resp.json()) == 1
    wq = resp.json()[0]
    assert wq["user_answer"] == "B" and len(wq["variants"]) == 2
    resp = client.post(f"/api/learn/wrongbook/{wq['id']}/regenerate",
                       headers=headers["student"])
    assert resp.json()["status"] == "generated"
    # 他人错题不可重新生成
    resp = client.post(f"/api/learn/wrongbook/{wq['id']}/regenerate",
                       headers=headers["student2"])
    assert resp.status_code == 404


def test_similar_students_and_courses(env):
    client, headers, tmp_path, Session, course = env
    # student 答错"梯度下降"、答对"线性回归"；student2 全对
    # （服务口径：仅列出"对方掌握而我未掌握"有借鉴项的学生——双方全对时 strengths 为空会被过滤）
    questions = client.get("/api/learn/diagnostic", headers=headers["student"]).json()["questions"]
    answers = [{"lesson_id": q["lesson_id"], "stem": q["stem"],
                "answer": "B" if q["knowledge_point"] == "梯度下降" else "A"}
               for q in questions]
    client.post("/api/learn/diagnostic", json={"answers": answers}, headers=headers["student"])
    client.post("/api/learn/diagnostic",
                json={"answers": [{"lesson_id": q["lesson_id"], "stem": q["stem"],
                                   "answer": "A"} for q in questions]},
                headers=headers["student2"])
    resp = client.get("/api/learn/similar", headers=headers["student"])
    assert resp.status_code == 200
    sims = resp.json()
    assert len(sims) == 1
    assert sims[0]["real_name"] == "student2"
    assert sims[0]["similarity"] > 0
    assert sims[0]["strengths"] == ["梯度下降"]  # 仅返回"对方掌握而我未掌握"的知识点名
    resp = client.get("/api/learn/courses", headers=headers["student"])
    assert resp.json() == [{"id": course.id, "name": "人工智能导论"}]


def test_kb_ask_records_ask_event(env, monkeypatch):
    client, headers, tmp_path, Session, course = env
    monkeypatch.setattr(kb_service, "hybrid_retrieve", lambda *a, **k: [])
    s = Session()
    kp = KnowledgePoint(name="梯度下降", description="")
    s.add(kp)
    s.commit()
    student = s.query(User).filter(User.username == "student").first()
    gen = kb_service.ask_stream("梯度下降的学习率怎么调？", student, s,
                                embedder=FakeEmbedder(), vector_store=FakeStore(),
                                reranker=None, gateway=FakeAskGateway())
    blocks = list(gen)
    assert any("event: done" in b for b in blocks)
    events = s.query(LearnEvent).filter(LearnEvent.user_id == student.id,
                                        LearnEvent.event_type == "ask").all()
    assert len(events) == 1 and abs(events[0].delta - 2.0) < 0.001
    # 教师提问不记事件
    teacher = s.query(User).filter(User.username == "teacher").first()
    gen2 = kb_service.ask_stream("梯度下降怎么学？", teacher, s,
                                 embedder=FakeEmbedder(), vector_store=FakeStore(),
                                 reranker=None, gateway=FakeAskGateway())
    list(gen2)
    assert s.query(LearnEvent).filter(LearnEvent.user_id == teacher.id).count() == 0
    # 画像事件记录失败不影响问答流（done 仍发出）
    monkeypatch.setattr(kb_service.learn_profile, "record_ask_events",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    gen3 = kb_service.ask_stream("梯度下降怎么学？", student, s,
                                 embedder=FakeEmbedder(), vector_store=FakeStore(),
                                 reranker=None, gateway=FakeAskGateway())
    assert any("event: done" in b for b in list(gen3))


def test_diagnostic_course_scoped(env):
    client, headers, *_ = env
    # 指定其他课程 → 无试题 404
    resp = client.get("/api/learn/diagnostic?course_id=999999", headers=headers["student"])
    assert resp.status_code == 404


def test_practice_prev_stem(env):
    client, headers, _, _, course = env
    url = (f"/api/learn/practice?kp=梯度下降&course_id={course.id}"
           f"&prev_stem=诊断梯度下降题0")
    resp = client.get(url, headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json()["stem"] != "诊断梯度下降题0"


def test_wrongbook_course_filter(env):
    """错题本按课程过滤（course_id 精确匹配）：同名知识点「决策树」的 B 课错题
    不泄漏进 A 课错题本；不传 course_id 全局兜底；响应结构不含 course_id。"""
    client, headers, _, Session, course = env
    from app.models.learn import KnowledgePoint, WrongQuestion
    s = Session()
    student = s.query(User).filter(User.username == "student").first()
    course_b = Course(name="课程B", subject="x", owner_id=1)
    s.add(course_b)
    s.flush()
    s.add_all([KnowledgePoint(name="决策树", course_id=course.id),
               KnowledgePoint(name="决策树", course_id=course_b.id)])
    s.flush()
    s.add_all([
        WrongQuestion(user_id=student.id, stem="错题A", user_answer="B",
                      correct_answer="A", knowledge_point="决策树",
                      course_id=course.id),
        WrongQuestion(user_id=student.id, stem="错题B", user_answer="B",
                      correct_answer="A", knowledge_point="决策树",
                      course_id=course_b.id),
    ])
    s.commit()
    resp = client.get(f"/api/learn/wrongbook?course_id={course.id}",
                      headers=headers["student"])
    assert resp.status_code == 200
    assert [w["stem"] for w in resp.json()] == ["错题A"]
    # 反方向：B 课错题本只有 B 课那条
    resp_b = client.get(f"/api/learn/wrongbook?course_id={course_b.id}",
                        headers=headers["student"])
    assert [w["stem"] for w in resp_b.json()] == ["错题B"]
    # 不传 course_id → 全局兜底（旧调用方兼容），且响应结构不含 course_id 字段
    resp_all = client.get("/api/learn/wrongbook", headers=headers["student"])
    items = resp_all.json()
    assert {w["stem"] for w in items} == {"错题A", "错题B"}
    assert all("course_id" not in w for w in items)
    s.close()
