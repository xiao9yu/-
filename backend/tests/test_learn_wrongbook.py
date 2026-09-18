# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""AIGC 错题本服务测试：登记/同步生成/失败保留/重新生成。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import WrongQuestion
from app.models.user import Role, User
from app.services import learn_wrongbook
from app.services.llm_gateway import LLMError

GOOD_JSON = {
    "解析": "先算梯度再更新参数。",
    "错误原因": "概念混淆：误把学习率当成迭代次数。",
    "变式题": [
        {"题干": "变式1：调整什么参数控制收敛速度？", "选项": ["A.学习率", "B.批大小"],
         "答案": "A", "解析": "学习率控制步长。"},
        {"题干": "变式2：学习率过小的后果？", "选项": ["A.收敛慢", "B.发散"],
         "答案": "A", "解析": "步长过小收敛缓慢。"},
    ],
}


class FakeLLM:
    def __init__(self, result):
        self._result = result

    def chat_json(self, messages, temperature=0.3):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'wrongbook.db'}")
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


def _kwargs():
    return dict(stem="学习率过大会导致什么？", options=["A.收敛慢", "B.震荡发散"],
                user_answer="A", correct_answer="B",
                knowledge_point="梯度下降", difficulty="中")


def test_add_wrong_question_generated(db, user):
    wq = learn_wrongbook.add_wrong_question(user, db=db, llm=FakeLLM(GOOD_JSON), **_kwargs())
    assert wq.status == "generated"
    assert wq.analysis == GOOD_JSON["解析"]
    assert wq.error_reason == GOOD_JSON["错误原因"]
    assert len(wq.variants) == 2
    assert wq.user_id == user.id


def test_add_wrong_question_llm_failure_keeps_record(db, user):
    """LLM 失败：错题保留（status=failed），不抛异常（接口正常返回）。"""
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM(LLMError("未配置 DEEPSEEK_API_KEY")), **_kwargs())
    assert wq.status == "failed"
    assert wq.analysis == "" and wq.variants == []
    assert db.get(WrongQuestion, wq.id) is not None


def test_add_wrong_question_bad_structure_keeps_record(db, user):
    """结构不完整（缺字段/变式题不足 2 道）→ 同样保留错题并置 failed。"""
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM({"解析": "只有解析"}), **_kwargs())
    assert wq.status == "failed"
    wq2 = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM({"解析": "x", "错误原因": "y", "变式题": [{"题干": "1"}]}), **_kwargs())
    assert wq2.status == "failed"


def test_variant_item_missing_fields_keeps_record_failed(db, user):
    """变式题条目缺字段（题干/选项/答案/解析）→ 同样保留错题并置 failed。"""
    bad = {"解析": "x", "错误原因": "y", "变式题": [
        {"题干": "v1", "选项": ["A", "B"], "答案": "A", "解析": ""},
        {"题干": "v2", "选项": ["A", "B"], "答案": "A"},  # 缺解析
    ]}
    wq = learn_wrongbook.add_wrong_question(user, db=db, llm=FakeLLM(bad), **_kwargs())
    assert wq.status == "failed"
    assert wq.analysis == "" and wq.variants == []


def test_list_and_regenerate(db, user):
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM(LLMError("未配置")), **_kwargs())
    assert wq.status == "failed"
    assert [w.id for w in learn_wrongbook.list_wrongbook(user, db)] == [wq.id]
    wq2 = learn_wrongbook.regenerate(user, wq.id, db, llm=FakeLLM(GOOD_JSON))
    assert wq2.status == "generated"
    assert len(wq2.variants) == 2
    # 重新生成再次失败 → 保持 failed，不抛异常
    wq3 = learn_wrongbook.regenerate(user, wq.id, db, llm=FakeLLM(LLMError("未配置")))
    assert wq3.status == "failed"


def test_regenerate_not_owner_404(db, user):
    other = User(username="s2", hashed_password="x", role=Role.student, real_name="王同学")
    db.add(other)
    db.commit()
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM(GOOD_JSON), **_kwargs())
    from app.core.exceptions import BizError
    with pytest.raises(BizError) as exc:
        learn_wrongbook.regenerate(other, wq.id, db, llm=FakeLLM(GOOD_JSON))
    assert exc.value.status_code == 404
    # 不存在同样 404
    with pytest.raises(BizError):
        learn_wrongbook.regenerate(user, 99999, db, llm=FakeLLM(GOOD_JSON))
