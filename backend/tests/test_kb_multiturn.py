# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""多轮问答测试：上下文进提示词、追问改写检索、会话落库与回放。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.chat import ChatMessage, ChatSession   # noqa: F401
from app.models.kb import KbChunk, KbDocument          # noqa: F401
from app.models.user import Role, User
from app.services import chat_service, kb_service


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


class FakeStore:
    def create_collection(self, name, dim): pass
    def upsert(self, name, ids, vectors, metadatas): pass

    def search(self, name, query_vector, top_k, filter_dict=None):
        return []

    def delete(self, name, ids): pass


class CapturingGateway:
    """记录每次喂给 LLM 的 messages，供断言上下文是否真的进了提示词。"""

    def __init__(self):
        self.calls: list[list[dict]] = []

    def chat_stream(self, messages, temperature=0.7):
        self.calls.append(messages)
        yield "学习率控制步长[1]。"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mt.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


@pytest.fixture
def patch_rag(monkeypatch):
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: FakeStore())
    gateway = CapturingGateway()
    monkeypatch.setattr(kb_service, "get_gateway", lambda: gateway)
    return gateway


def _student(uid=5):
    u = User(username="s", hashed_password="x", role=Role.student)
    u.id = uid
    return u


def _seed_doc(db, monkeypatch):
    """直接落一条 ready 公共文档 + 文本块：多轮逻辑测试不依赖真实解析与向量库。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: FakeStore())
    doc = KbDocument(title="demo.pdf", file_id=1, scope="public", owner_id=1, status="ready")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(KbChunk(id="a" * 32, document_id=doc.id, kind="text",
                   text="梯度下降的学习率控制步长", source="demo.pdf", meta={}))
    db.commit()


def test_single_turn_without_session_keeps_old_contract(db, patch_rag, monkeypatch):
    """不传 session：行为与单轮一致——不落库、无历史消息、提示词只有 system+user。"""
    _seed_doc(db, monkeypatch)
    events = list(kb_service.answer_events("什么是梯度下降", _student(), db))
    assert events[-1] == ("done", {})
    assert db.query(ChatSession).count() == 0
    assert db.query(ChatMessage).count() == 0
    assert [m["role"] for m in patch_rag.calls[0]] == ["system", "user"]


def test_history_is_injected_into_prompt(db, patch_rag, monkeypatch):
    """多轮：历史轮次作为正式对话消息插在 system 与当前 user 之间。"""
    _seed_doc(db, monkeypatch)
    user = _student()
    session = chat_service.create_session(db, user, "梯度下降的学习率怎么选")
    chat_service.append_turn(db, session, "梯度下降的学习率怎么选", "按经验取 0.01[1]。")

    list(kb_service.answer_events("那它设大了会怎样", user, db, session=session))
    msgs = patch_rag.calls[0]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"] == "梯度下降的学习率怎么选"
    assert msgs[2]["content"] == "按经验取 0.01。"          # 历史里的 [1] 已剥离
    assert "对话历史" in msgs[0]["content"]                # 历史提示词生效
    assert msgs[3]["content"].startswith("【问题】那它设大了会怎样")
    # 本轮问答已落库，轮数 +1
    assert session.turns == 2
    assert db.query(ChatMessage).count() == 4


def test_followup_rewrites_retrieval_query(db, patch_rag, monkeypatch):
    """追问检索改写：指代型追问带上上一轮问题一起检索，否则必然空手。"""
    _seed_doc(db, monkeypatch)
    user = _student()
    session = chat_service.create_session(db, user, "梯度下降的学习率怎么选")
    chat_service.append_turn(db, session, "梯度下降的学习率怎么选", "取 0.01。")
    seen: list[str] = []
    monkeypatch.setattr(kb_service, "hybrid_retrieve",
                        lambda q, *a, **k: seen.append(q) or [])
    list(kb_service.answer_events("那它设大了会怎样", user, db, session=session))
    assert seen and seen[0].startswith("梯度下降的学习率怎么选")
    assert "那它设大了会怎样" in seen[0]


def test_citations_persisted_for_replay(db, patch_rag, monkeypatch):
    """引用随历史落库：翻页/刷新后仍能还原每一轮的溯源。"""
    _seed_doc(db, monkeypatch)
    user = _student()
    session = chat_service.create_session(db, user, "什么是梯度下降")
    list(kb_service.answer_events("什么是梯度下降", user, db, session=session))
    rows = chat_service.list_messages(db, session)
    assistant = [m for m in rows if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == "学习率控制步长[1]。"
    assert assistant[0]["citations"] and assistant[0]["citations"][0]["source"] == "demo.pdf"


def test_llm_failure_does_not_persist_turn(db, patch_rag, monkeypatch):
    """LLM 失败发 error 且不落库：历史里不应出现空回答轮次。"""
    _seed_doc(db, monkeypatch)
    from app.services.llm_gateway import LLMError

    class BadGateway:
        def chat_stream(self, messages, temperature=0.7):
            raise LLMError("未配置 DEEPSEEK_API_KEY")
            yield  # pragma: no cover

    monkeypatch.setattr(kb_service, "get_gateway", lambda: BadGateway())
    user = _student()
    session = chat_service.create_session(db, user, "什么是梯度下降")
    events = list(kb_service.answer_events("什么是梯度下降", user, db, session=session))
    assert events[-1][0] == "error"
    assert db.query(ChatMessage).count() == 0
    assert session.turns == 0
