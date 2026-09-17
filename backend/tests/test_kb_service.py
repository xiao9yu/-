# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库入库服务测试：上传解析向量化、列表、删除、权限。"""
import io
from pathlib import Path

import pytest
import pymupdf
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.kb import KbChunk, KbDocument
from app.models.user import Role, User
from app.services import kb_service
from app.services.kb_service import PUBLIC_COLLECTION, add_document, delete_document, list_documents, private_collection


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def _teacher():
    u = User(username="t", hashed_password="x", role=Role.teacher)
    u.id = 3
    return u


def _admin():
    u = User(username="a", hashed_password="x", role=Role.admin)
    u.id = 1
    return u


def _student():
    u = User(username="s", hashed_password="x", role=Role.student)
    u.id = 5
    return u


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[float((i + 1) % 8) / 8 for _ in range(self.dim)] for i in range(len(texts))]

    def embed_query(self, text):
        return self.embed_texts([text])[0]


def _sample_pdf(path: Path):
    """两页演示 PDF（中文文本，保证 BM25 中文分词可命中）。"""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "梯度下降是机器学习核心优化算法", fontname="china-s")
    page = doc.new_page()
    page.insert_text((72, 72), "反向传播基于链式法则计算梯度", fontname="china-s")
    doc.save(str(path))
    doc.close()


def _upload_pdf(path: Path):
    return UploadFile(filename="demo.pdf", file=io.BytesIO(path.read_bytes()))


def test_add_document_private_indexes_into_user_collection(tmp_path, db, monkeypatch):
    holder = {}   # 捕获调用期使用的向量库实例（lambda 每次新建则无法断言落盘）
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store",
                        lambda: holder.setdefault("store", _FakeStore(tmp_path)))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    doc = add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)
    assert doc.scope == "private" and doc.status == "ready" and doc.chunk_count > 0
    rows = db.query(KbChunk).filter(KbChunk.document_id == doc.id).all()
    assert rows and all(r.source == "demo.pdf" for r in rows)
    assert private_collection(3) == "kb_user_3"
    # 向量已写入用户私有集合
    assert "kb_user_3" in holder["store"].ids


def test_add_document_public_only_admin(tmp_path, db, monkeypatch):
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    from app.core.exceptions import BizError
    with pytest.raises(BizError, match="仅管理员"):
        add_document(_upload_pdf(pdf), "public", _teacher(), tmp_path, db)
    doc = add_document(_upload_pdf(pdf), "public", _admin(), tmp_path, db)
    assert doc.scope == "public"
    assert PUBLIC_COLLECTION == "kb_public"


def test_add_document_empty_parse_rejected_and_rolled_back(tmp_path, db, monkeypatch):
    """解析为空（.doc/.ppt/.xls 等）拒绝上传且不留文件与记录。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    monkeypatch.setattr(kb_service, "parse_document", lambda p: [])
    file = UploadFile(filename="legacy.doc", file=io.BytesIO(b"x"))
    from app.core.exceptions import BizError
    with pytest.raises(BizError, match="转换"):
        add_document(file, "private", _teacher(), tmp_path, db)
    assert db.query(KbDocument).count() == 0
    from app.models.file import FileRecord
    assert db.query(FileRecord).count() == 0
    # 上传产物已全部清除；tmp_path 中仅剩本测试夹具自建的 kb.db（简报原断言 ==[] 与
    # 夹具自身落盘 kb.db 矛盾，改为精确集合断言，多余上传文件同样会使断言失败）
    assert {p.name for p in tmp_path.iterdir()} == {"kb.db"}


def test_add_document_embedder_failure_marks_failed(tmp_path, db, monkeypatch):
    """向量化失败时文档保留 status=failed 并记录原因，EmbedderError 上抛。"""
    from app.services.embeddings import EmbedderError
    monkeypatch.setattr(kb_service, "get_embedder", lambda: (_ for _ in ()).throw(
        EmbedderError("嵌入模型加载失败：offline。HF_ENDPOINT=https://hf-mirror.com")))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    with pytest.raises(EmbedderError):
        add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)
    doc = db.query(KbDocument).first()
    assert doc is not None and doc.status == "failed" and "HF_ENDPOINT" in doc.error


def test_list_documents_scope_visibility(tmp_path, db, monkeypatch):
    """列表可见性：本人私有 + 全部公共，他人私有不可见。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)   # 教师私有
    add_document(_upload_pdf(pdf), "public", _admin(), tmp_path, db)      # 公共
    add_document(_upload_pdf(pdf), "private", _admin(), tmp_path, db)     # admin 私有
    mine = list_documents(_teacher(), db)
    assert {d.scope + str(d.owner_id) for d in mine} == {"private3", "public1"}
    assert len(list_documents(_student(), db)) == 1  # 学生只见公共库


def test_delete_document_permissions_and_cleanup(tmp_path, db, monkeypatch):
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    doc = add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)
    from app.core.exceptions import BizError
    with pytest.raises(BizError, match="无权"):
        delete_document(doc.id, _student(), tmp_path, db)
    with pytest.raises(BizError):
        delete_document(999, _teacher(), tmp_path, db)
    delete_document(doc.id, _teacher(), tmp_path, db)
    assert db.query(KbDocument).count() == 0
    assert db.query(KbChunk).count() == 0
    from app.models.file import FileRecord
    assert db.query(FileRecord).count() == 0
    # 上传产物已全部清除；tmp_path 中仅剩测试样本 demo.pdf 与夹具库文件 kb.db
    # （简报原断言 ==[] 与夹具自身落盘矛盾，改为精确集合断言，多余上传文件同样会使断言失败）
    assert {p.name for p in tmp_path.iterdir()} == {"kb.db", "demo.pdf"}


class _FakeStore:
    """极简落盘向量库替身：方法签名对齐 FaissVectorStore。"""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.indexes = {}
        self.ids = {}
        self.metas = {}

    def _load(self):
        pass

    def create_collection(self, name, dim):
        self.indexes.setdefault(name, [])
        self.ids.setdefault(name, [])
        self.metas.setdefault(name, [])

    def upsert(self, name, ids, vectors, metadatas):
        self.create_collection(name, 8)
        self.ids[name].extend(ids)
        self.metas[name].extend(metadatas)

    def search(self, name, query_vector, top_k, filter_dict=None):
        return []

    def delete(self, name, ids):
        for i in ids:
            if i in self.ids.get(name, []):
                pos = self.ids[name].index(i)
                del self.ids[name][pos]
                del self.metas[name][pos]
