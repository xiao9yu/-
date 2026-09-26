# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17 扩展：知识库出题)
"""知识库出题测试：prompt 组装/结构校验/生成即入学习题库/检索空手 404/LLM 失败 502。"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import BizError
from app.services import kb_service, prep_generator
from app.services.llm_gateway import LLMError

EXERCISES_KB = {
    "习题": [
        {"题干": "知识库出题演示题1", "选项": ["A.甲", "B.乙", "C.丙", "D.丁"],
         "答案": "A", "解析": "解析1", "知识点": "线性表", "难度": "易"},
        {"题干": "知识库出题演示题2", "选项": ["A.甲", "B.乙", "C.丙", "D.丁"],
         "答案": "B", "解析": "解析2", "知识点": "栈与队列", "难度": "中"},
    ]
}


class _FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat_json(self, messages, temperature=0.3):
        self.calls.append({"messages": messages, "temperature": temperature})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _FakeHit:
    def __init__(self, text, source="数据结构与算法知识库.md"):
        self.chunk = SimpleNamespace(text=text, source=source, page=1)


def _register_login(client, username, role):
    client.post("/api/auth/register", json={"username": username, "password": "pass123456",
                                            "role": role, "real_name": "测试"})
    resp = client.post("/api/auth/login", json={"username": username, "password": "pass123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_course(client, headers, name="人工智能导论"):
    resp = client.post("/api/prep/courses", json={"name": name, "subject": "人工智能",
                                                  "description": "测试课程"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


def test_generate_kb_exercises_prompt_and_temperature():
    llm = _FakeLLM(EXERCISES_KB)
    result = prep_generator.generate_kb_exercises(
        course_name="数据结构与算法", subject="数据结构与算法", chapter="第3章",
        knowledge_points=["线性表", "栈与队列"], count=2, difficulty="中",
        kb_material="【资料】线性表是有限序列。", llm=llm)
    assert result == EXERCISES_KB
    prep_generator.validate_exercises(result)  # 结构校验通过
    prompt = llm.calls[0]["messages"][-1]["content"]
    assert "数据结构与算法" in prompt and "线性表" in prompt
    assert "题目数量：2 道" in prompt and "难度：中" in prompt
    assert "线性表是有限序列" in prompt and "仅依据" in prompt
    assert llm.calls[0]["temperature"] == 0.3


def test_generate_kb_exercises_validation_missing_keys():
    llm = _FakeLLM({"习题": [{"题干": "只有题干"}]})
    result = prep_generator.generate_kb_exercises(
        "课程", "学科", "章", ["知识点"], 1, "", "资料", llm=llm)
    with pytest.raises(BizError):
        prep_generator.validate_exercises(result)


def test_kb_exercises_generate_saves_to_lesson(client, monkeypatch):
    """生成即入学习题库：自动落 exercises lesson；同题干重复生成去重。"""
    headers = _register_login(client, "t_kb", "teacher")
    course = _create_course(client, headers, name="数据结构与算法")
    llm = _FakeLLM(EXERCISES_KB)
    monkeypatch.setattr(prep_generator, "get_gateway", lambda: llm)
    monkeypatch.setattr(kb_service, "retrieve_chunks",
                        lambda *a, **kw: [_FakeHit("线性表是有限序列。"),
                                          _FakeHit("栈是先进后出。")])
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "chapter": "第3章",
                             "knowledge_points": ["线性表"], "count": 2, "difficulty": "中"},
                       headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "kb_exercises"
    assert body["lesson"]["added"] == 2 and body["lesson"]["total"] == 2
    lessons = client.get(f"/api/prep/courses/{course['id']}/lessons",
                         headers=headers).json()
    assert len(lessons) == 1
    assert lessons[0]["title"] == "数据结构与算法知识库生成习题"
    assert lessons[0]["lesson_type"] == "exercises"
    assert len(lessons[0]["content_json"]["习题"]) == 2
    # 再次生成同批题：同题干去重，不重复追加
    resp2 = client.post(f"/api/prep/courses/{course['id']}/generate",
                        json={"type": "kb_exercises", "knowledge_points": ["线性表"],
                              "count": 2, "difficulty": ""},
                        headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["lesson"]["added"] == 0
    assert resp2.json()["lesson"]["total"] == 2
    # 追加分支：新一批 = 1 道旧题 + 1 道新题 → 仅追加新题
    mixed = {"习题": [EXERCISES_KB["习题"][0],
                      {"题干": "知识库出题演示题3", "选项": ["A.甲", "B.乙", "C.丙", "D.丁"],
                       "答案": "C", "解析": "解析3", "知识点": "线性表", "难度": "中"}]}
    monkeypatch.setattr(prep_generator, "get_gateway", lambda: _FakeLLM(mixed))
    resp3 = client.post(f"/api/prep/courses/{course['id']}/generate",
                        json={"type": "kb_exercises", "knowledge_points": ["线性表"],
                              "count": 2, "difficulty": ""},
                        headers=headers)
    assert resp3.status_code == 200
    assert resp3.json()["lesson"]["added"] == 1
    assert resp3.json()["lesson"]["total"] == 3


def test_kb_exercises_retrieval_passes_reranker(client, monkeypatch):
    """知识库出题检索接精排（与问答检索同路径）：retrieve_chunks 收到非空 reranker。"""
    from app.api import prep as prep_api
    headers = _register_login(client, "t_kb4", "teacher")
    course = _create_course(client, headers, name="数据结构与算法")
    sentinel = object()
    monkeypatch.setattr(prep_api, "get_reranker", lambda: sentinel)
    captured = {}

    def fake_retrieve(user, query, db, *, top_k=8, reranker=None):
        captured["reranker"] = reranker
        return [_FakeHit("线性表是有限序列。")]

    monkeypatch.setattr(kb_service, "retrieve_chunks", fake_retrieve)
    monkeypatch.setattr(prep_generator, "get_gateway", lambda: _FakeLLM(EXERCISES_KB))
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "knowledge_points": ["线性表"],
                             "count": 2, "difficulty": "中"},
                       headers=headers)
    assert resp.status_code == 200
    assert captured["reranker"] is sentinel


def test_kb_exercises_no_hits_404(client, monkeypatch):
    headers = _register_login(client, "t_kb2", "teacher")
    course = _create_course(client, headers)
    monkeypatch.setattr(kb_service, "retrieve_chunks", lambda *a, **kw: [])
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "knowledge_points": ["梯度下降"]},
                       headers=headers)
    assert resp.status_code == 404
    assert "知识库" in resp.json()["detail"]


def test_kb_exercises_llm_error_502(client, monkeypatch):
    headers = _register_login(client, "t_kb3", "teacher")
    course = _create_course(client, headers)
    monkeypatch.setattr(prep_generator, "get_gateway",
                        lambda: _FakeLLM(LLMError("密钥未配置")))
    monkeypatch.setattr(kb_service, "retrieve_chunks",
                        lambda *a, **kw: [_FakeHit("资料")])
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "knowledge_points": ["线性表"]},
                       headers=headers)
    assert resp.status_code == 502


def test_kp_label_list_falls_back_to_course_kps():
    """出题覆盖清单：教师填写值只取与课程清单精确一致的，否则用课程全清单。"""
    from app.api.prep import _kp_label_list
    course_kps = ["线性表", "栈与队列", "串与数组"]
    assert _kp_label_list([], course_kps) == course_kps
    assert _kp_label_list(["线性表"], course_kps) == ["线性表"]
    assert _kp_label_list(["线性表", "不存在的点"], course_kps) == ["线性表"]
    assert _kp_label_list(["不存在的点"], course_kps) == course_kps


def test_align_kp_names_maps_llm_labels_to_course_kps():
    """练习按知识点精确匹配抽题：LLM 自创/改写标签必须对齐回课程清单，否则题永远抽不到。"""
    from app.api.prep import _align_kp_names
    course_kps = ["线性表", "栈与队列", "串与数组", "数据结构基础", "图", "递归与分治"]
    questions = [
        {"题干": "q1", "知识点": "线性表"},             # 精确匹配：不动
        {"题干": "q2", "知识点": "串"},                 # 包含关系 → 串与数组
        {"题干": "q3", "知识点": "数据结构与算法基础"},  # 相似度兜底 → 数据结构基础
        {"题干": "q4", "知识点": "图"},                 # 精确匹配：不动
    ]
    out = _align_kp_names(questions, course_kps)
    assert [q["知识点"] for q in out] == ["线性表", "串与数组", "数据结构基础", "图"]
