# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库 API 测试：上传/列表/删除/图片/流式问答/权限。"""
import io

import pymupdf
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import app
from app.api import deps
from app.models.user import Role, User
from app.services import kb_service


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


class FakeStore:
    """进程内存向量库替身。"""

    def __init__(self):
        self.data = {}

    def create_collection(self, name, dim):
        self.data.setdefault(name, [])

    def upsert(self, name, ids, vectors, metadatas):
        self.data.setdefault(name, []).extend(metadatas)

    def search(self, name, query_vector, top_k, filter_dict=None):
        return []

    def delete(self, name, ids):
        pass


class FakeGateway:
    def chat_stream(self, messages, temperature=0.7):
        yield "助教回答片段一"
        yield "片段二"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时 DB + 假向量库/嵌入模型 + 三个角色 headers + Session 工厂。"""
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
    from app.config import settings
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))  # 上传不落真实 uploads/
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: FakeStore())
    # 测试禁加载真实 bge-reranker（约束）：路由内 get_reranker 置 None 走降级路径
    from app.api import kb as kb_api
    monkeypatch.setattr(kb_api, "get_reranker", lambda: None)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    # 建三个用户
    from app.core.security import create_access_token, hash_password
    s = Session()
    headers = {}
    for name, role in [("teacher", Role.teacher), ("student", Role.student), ("admin", Role.admin)]:
        u = User(username=name, hashed_password=hash_password("p"), role=role, real_name=name)
        s.add(u)
        s.commit()
        s.refresh(u)
        headers[name] = {"Authorization": f"Bearer {create_access_token(u.id, u.role.value)}"}
    s.close()
    yield client, headers, tmp_path, Session
    app.dependency_overrides.clear()


def _sample_pdf(path):
    """一页演示 PDF（中文文本，保证 BM25 命中）。"""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "梯度下降是机器学习核心优化算法", fontname="china-s")
    doc.save(str(path))
    doc.close()


def _upload(client, headers, scope="private"):
    import tempfile
    from pathlib import Path
    pdf = Path(tempfile.mkdtemp()) / "demo.pdf"
    _sample_pdf(pdf)
    with open(pdf, "rb") as f:
        return client.post("/api/kb/documents", files={"file": ("demo.pdf", f, "application/pdf")},
                           data={"scope": scope}, headers=headers)


def test_upload_and_list_documents(env):
    client, headers, _, _ = env
    r = _upload(client, headers["teacher"])
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.json()["chunk_count"] > 0
    r = client.get("/api/kb/documents", headers=headers["student"])
    assert r.status_code == 200 and r.json() == []      # 教师私有，学生不可见
    r = client.get("/api/kb/documents", headers=headers["teacher"])
    assert r.status_code == 200 and len(r.json()) == 1


def test_public_upload_admin_only(env):
    client, headers, _, _ = env
    assert _upload(client, headers["teacher"], scope="public").status_code == 403
    r = _upload(client, headers["admin"], scope="public")
    assert r.status_code == 200
    assert client.get("/api/kb/documents", headers=headers["student"]).json()[0]["scope"] == "public"


def test_delete_permissions(env):
    client, headers, _, _ = env
    doc_id = _upload(client, headers["teacher"]).json()["id"]
    assert client.delete(f"/api/kb/documents/{doc_id}", headers=headers["student"]).status_code == 403
    assert client.delete(f"/api/kb/documents/{doc_id}", headers=headers["teacher"]).status_code == 200
    assert client.get("/api/kb/documents", headers=headers["teacher"]).json() == []


def test_chunk_image_endpoint_permissions(env):
    """图片端点：公共库 chunk 全员可看，他人私有 403。"""
    client, headers, tmp_path, Session = env
    doc_id = _upload(client, headers["admin"], scope="public").json()["id"]
    from app.models.kb import KbChunk
    img = tmp_path / "img.png"
    img.write_bytes(b"PNGDATA")
    chunk = KbChunk(id="e" * 32, document_id=doc_id, kind="image", text="公式图",
                    source="demo.pdf", meta={"image_path": str(img)})
    s = Session()
    s.add(chunk)
    s.commit()
    s.close()
    r = client.get(f"/api/kb/chunks/{'e' * 32}/image", headers=headers["student"])
    assert r.status_code == 200 and r.content == b"PNGDATA"
    # 私有库他人 chunk → 403
    doc_id2 = _upload(client, headers["teacher"]).json()["id"]
    chunk2 = KbChunk(id="f" * 32, document_id=doc_id2, kind="image", text="私有图",
                     source="demo.pdf", meta={"image_path": str(img)})
    s = Session()
    s.add(chunk2)
    s.commit()
    s.close()
    assert client.get(f"/api/kb/chunks/{'f' * 32}/image", headers=headers["student"]).status_code == 403


def test_ask_stream_sse(env):
    client, headers, _, _ = env
    _upload(client, headers["admin"], scope="public")
    import app.services.kb_service as ks
    from unittest import mock
    with mock.patch.object(ks, "get_gateway", lambda: FakeGateway()):
        r = client.post("/api/kb/ask", json={"question": "什么是梯度下降"}, headers=headers["student"])
    assert r.status_code == 200
    body = r.text
    assert "event: citations" in body
    assert "demo.pdf" in body
    assert "助教回答片段一" in body
    assert "event: done" in body


def test_ask_empty_question_400(env):
    client, headers, _, _ = env
    r = client.post("/api/kb/ask", json={"question": "   "}, headers=headers["student"])
    assert r.status_code == 400
