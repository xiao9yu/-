# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""多轮会话服务测试：会话增删查、上下文装载、追问检索改写。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.chat import ChatMessage, ChatSession   # noqa: F401  建表需先导入模型
from app.models.user import Role, User
from app.services import chat_service


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def _user(uid=3, role=Role.student):
    u = User(username="s", hashed_password="x", role=role)
    u.id = uid
    return u


def _other(uid=9):
    u = User(username="o", hashed_password="x", role=Role.teacher)
    u.id = uid
    return u


def test_create_session_title_truncated(db):
    s = chat_service.create_session(db, _user(), "什么是" + "梯度下降" * 20)
    assert s.id is not None and s.user_id == 3 and s.turns == 0
    assert len(s.title) == chat_service._SESSION_TITLE_MAX


def test_resolve_session_new_when_missing_or_foreign(db):
    u = _user()
    # 未传 session_id → 新建
    s1 = chat_service.resolve_session(db, u, None, "第一个问题")
    assert s1.id is not None
    # 传自己的 → 续接同一个
    s2 = chat_service.resolve_session(db, u, s1.id, "追问")
    assert s2.id == s1.id
    # 传他人的 → 静默新建，不越权访问
    foreign = chat_service.create_session(db, _other(), "别人的会话")
    s3 = chat_service.resolve_session(db, u, foreign.id, "试探")
    assert s3.id != foreign.id and s3.user_id == u.id
    # 传不存在的 id → 同样新建
    s4 = chat_service.resolve_session(db, u, 999999, "再试探")
    assert s4.id not in (s1.id, foreign.id)


def test_append_turn_and_recent_history(db):
    u = _user()
    s = chat_service.create_session(db, u, "梯度下降是什么")
    chat_service.append_turn(db, s, "梯度下降是什么", "它是一种优化算法[1]。",
                             [{"ref_no": 1, "source": "demo.pdf"}])
    chat_service.append_turn(db, s, "那学习率呢", "学习率控制步长。")
    assert s.turns == 2
    hist = chat_service.recent_history(db, s)
    assert [h["role"] for h in hist] == ["user", "assistant", "user", "assistant"]
    # assistant 文本去掉 [n]：提示词每轮重新编号，带旧编号会被当成已存在资料误引用
    assert hist[1]["content"] == "它是一种优化算法。"
    assert hist[0]["content"] == "梯度下降是什么"


def test_recent_history_limits_to_requested_turns(db):
    u = _user()
    s = chat_service.create_session(db, u, "q1")
    for i in range(1, 6):
        chat_service.append_turn(db, s, f"问题{i}", f"回答{i}")
    hist = chat_service.recent_history(db, s, turns=2)
    assert [h["content"] for h in hist] == ["问题4", "回答4", "问题5", "回答5"]


def test_list_messages_keeps_citations(db):
    u = _user()
    s = chat_service.create_session(db, u, "q")
    cites = [{"ref_no": 1, "source": "demo.pdf", "text": "原文"}]
    chat_service.append_turn(db, s, "q", "a[1]", cites)
    msgs = chat_service.list_messages(db, s)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["citations"] == cites


def test_list_sessions_only_mine(db):
    u = _user()
    chat_service.create_session(db, u, "我的")
    chat_service.create_session(db, _other(), "别人的")
    rows = chat_service.list_sessions(db, u)
    assert [r["title"] for r in rows] == ["我的"]


def test_delete_session_cascades_messages_and_checks_owner(db):
    u = _user()
    s = chat_service.create_session(db, u, "q")
    chat_service.append_turn(db, s, "q", "a")
    assert chat_service.delete_session(db, _other(), s.id) is False
    assert db.query(ChatMessage).count() == 2      # 越权删除无副作用
    assert chat_service.delete_session(db, u, s.id) is True
    assert db.query(ChatSession).count() == 0
    assert db.query(ChatMessage).count() == 0


def test_get_owned_session_returns_none_for_foreign(db):
    s = chat_service.create_session(db, _other(), "别人的")
    assert chat_service.get_owned_session(db, _user(), s.id) is None
    assert chat_service.get_owned_session(db, _other(), s.id) is not None


# ---------- 追问检索改写 ----------
def _hist(*pairs):
    out = []
    for q, a in pairs:
        out.append({"role": "user", "content": q})
        out.append({"role": "assistant", "content": a})
    return out


def test_rewrite_query_without_history_passthrough():
    assert chat_service.rewrite_query("什么是梯度下降", []) == "什么是梯度下降"


def test_rewrite_query_merges_anaphoric_followup():
    hist = _hist(("梯度下降的学习率怎么选", "按经验取 0.01。"))
    out = chat_service.rewrite_query("那它设大了会怎样", hist)
    assert out.startswith("梯度下降的学习率怎么选")
    assert "那它设大了会怎样" in out


def test_rewrite_query_merges_short_followup():
    hist = _hist(("什么是反向传播", "链式法则。"))
    # 短句（≤14 字）同样视为追问，即便不含指代词
    assert chat_service.rewrite_query("举个例子", hist) == "什么是反向传播 举个例子"


def test_rewrite_query_keeps_standalone_question():
    hist = _hist(("什么是梯度下降", "优化算法。"))
    q = "过拟合的常见解决手段有哪些，请分别说明各自适用场景"
    assert chat_service.rewrite_query(q, hist) == q


def test_rewrite_query_uses_latest_user_turn():
    hist = _hist(("第一问", "答一"), ("第二问", "答二"))
    out = chat_service.rewrite_query("那为什么", hist)
    assert out.startswith("第二问")
