# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库数据模型测试：文档登记与多模态知识块。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.kb import KbChunk, KbDocument


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def test_kb_document_crud_and_defaults(db):
    doc = KbDocument(title="教材.pdf", file_id=1, scope="private", owner_id=3)
    db.add(doc)
    db.commit()
    got = db.get(KbDocument, doc.id)
    assert got.scope == "private"
    assert got.status == "ready"
    assert got.error == ""
    assert got.chunk_count == 0
    assert got.created_at is not None


def test_kb_chunk_kinds_and_meta(db):
    """多模态知识块：kind 区分 text/table/image，meta 存 image_path 等。"""
    c1 = KbChunk(id="a" * 32, document_id=1, kind="text", text="梯度下降",
                 source="教材.pdf", page=3)
    c2 = KbChunk(id="b" * 32, document_id=1, kind="image", text="",
                 source="教材.pdf", page=3, meta={"image_path": "uploads/extracted/x.png", "file_id": 1})
    db.add_all([c1, c2])
    db.commit()
    got = db.get(KbChunk, "a" * 32)
    assert got.text == "梯度下降"
    assert got.source == "教材.pdf"
    assert db.get(KbChunk, "b" * 32).meta["image_path"].endswith("x.png")


def test_kb_document_public_scope(db):
    db.add(KbDocument(title="公共库资料.pdf", file_id=2, scope="public", owner_id=1))
    db.commit()
    assert db.query(KbDocument).filter(KbDocument.scope == "public").count() == 1
