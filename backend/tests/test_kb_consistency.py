# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库一致性自检与修复测试（向量库 ↔ kb_chunks）。

背景（本机实测）：`人工智能导论知识库.pdf` 在 kb_chunks 有 3 块、文档 status=ready，
但向量库里 0/3。成因是 FAISS 实现把集合常驻内存、每次 upsert 整库覆盖写——
某次启动没能载入该集合时会建出空集合并把空集合写回磁盘，旧向量永久消失且无报错。
这里把"能发现"和"能修好"两件事钉住。
"""
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.kb import KbChunk, KbDocument
from app.services import kb_service
from app.services.kb_service import PUBLIC_COLLECTION, verify_consistency, repair_consistency
from app.services.vector_store import FaissVectorStore


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    store = FaissVectorStore(data_dir=tmp_path / "faiss")
    yield db, store, FakeEmbedder()
    db.close()
    Base.metadata.drop_all(engine)


def _add_doc(db, store, emb, *, title="演示.pdf", scope="public", owner_id=1,
             n=3, indexed=None, chunk_count=None):
    """造一份「已入库」的文档：DB 落 n 块，向量库只落 indexed 块（默认全落）。"""
    doc = KbDocument(title=title, file_id=1, scope=scope, owner_id=owner_id,
                     status="ready", chunk_count=n if chunk_count is None else chunk_count)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    rows = [KbChunk(id=uuid.uuid4().hex[:12], document_id=doc.id, kind="text",
                    text=f"{title} 第 {i} 段", source=title, page=i + 1, meta={})
            for i in range(n)]
    db.add_all(rows)
    db.commit()

    col = PUBLIC_COLLECTION if scope == "public" else f"kb_user_{owner_id}"
    store.create_collection(col, emb.dim)
    k = n if indexed is None else indexed
    if k:
        store.upsert(col, ids=[c.id for c in rows[:k]],
                     vectors=[emb.embed_query("x")] * k,
                     metadatas=[{"chunk_id": c.id, "source": title} for c in rows[:k]])
    return doc, rows, col


def test_verify_ok_when_consistent(env):
    db, store, emb = env
    _add_doc(db, store, emb, n=3)
    rep = verify_consistency(db, vector_store=store)
    assert rep["ok"] is True
    assert rep["problems"] == []
    assert rep["summary"]["n_missing"] == 0
    assert rep["summary"]["n_orphan"] == 0
    assert rep["collections"][0] == {
        "name": PUBLIC_COLLECTION, "expected": 3, "in_store": 3,
        "missing": 0, "orphan": 0, "missing_ids": [], "orphan_ids": [],
    }


def test_verify_detects_missing_vectors(env):
    """本机真实缺陷的形态：文档 ready、块在表里，向量却缺。"""
    db, store, emb = env
    doc, rows, col = _add_doc(db, store, emb, n=3, indexed=1)

    rep = verify_consistency(db, vector_store=store)
    assert rep["ok"] is False
    assert rep["summary"]["n_missing"] == 2
    assert rep["collections"][0]["missing"] == 2
    assert set(rep["collections"][0]["missing_ids"]) == {c.id for c in rows[1:]}
    assert rep["documents"][0]["id"] == doc.id
    assert rep["documents"][0]["indexed"] == 1
    assert any("无向量" in p for p in rep["problems"])


def test_verify_detects_orphan_vectors(env):
    """向量库里有、kb_chunks 里没有的残留（删文档只删了一半等）。"""
    db, store, emb = env
    _add_doc(db, store, emb, n=2)
    store.upsert(PUBLIC_COLLECTION, ids=["ghost-1"], vectors=[[0.125] * 8],
                 metadatas=[{"chunk_id": "ghost-1"}])

    rep = verify_consistency(db, vector_store=store)
    assert rep["ok"] is False
    assert rep["summary"]["n_orphan"] == 1
    assert rep["collections"][0]["orphan_ids"] == ["ghost-1"]
    assert any("无对应行" in p for p in rep["problems"])


def test_verify_detects_chunk_count_mismatch(env):
    """文档记账不符（chunk_count 与实际块数不一致）。"""
    db, store, emb = env
    doc, _, _ = _add_doc(db, store, emb, n=3, chunk_count=99)
    rep = verify_consistency(db, vector_store=store)
    assert rep["ok"] is False
    assert any("chunk_count=99" in p for p in rep["problems"])
    assert doc.id in [d["id"] for d in rep["documents"]]


def test_verify_detects_phantom_ready_document(env):
    """ready 但一块都没有的幻影文档。"""
    db, store, emb = env
    doc = KbDocument(title="空.pdf", file_id=1, scope="public", owner_id=1,
                     status="ready", chunk_count=0)
    db.add(doc)
    db.commit()
    rep = verify_consistency(db, vector_store=store)
    assert rep["ok"] is False
    assert any("幻影文档" in p for p in rep["problems"])


def test_verify_flags_locked_collection(env, tmp_path):
    """集合载入失败被锁定时，自检必须点明（写入会被拒绝）。"""
    db, store, emb = env
    _add_doc(db, store, emb, n=2)
    (tmp_path / "faiss" / f"{PUBLIC_COLLECTION}.meta.json").unlink()

    broken = FaissVectorStore(data_dir=tmp_path / "faiss")
    rep = verify_consistency(db, vector_store=broken)
    assert rep["ok"] is False
    assert rep["summary"]["locked_collections"] == [PUBLIC_COLLECTION]
    assert any("锁定" in p for p in rep["problems"])
    # 锁定集合的 id 未知（None），不能当成"空"而误报 missing
    assert rep["collections"][0]["missing"] is None
    assert rep["documents"] == []


def test_verify_marks_unsupported_store(env):
    """存储后端不实现枚举能力时标注"不支持"，而不是抛错或误判为空。"""
    db, store, emb = env
    _add_doc(db, store, emb, n=2)

    class DumbStore:
        def search(self, *a, **k):
            return []

    rep = verify_consistency(db, vector_store=DumbStore())
    assert rep["summary"]["unsupported_collections"] == [PUBLIC_COLLECTION]
    assert any("无法枚举" in n for n in rep["notes"])
    assert rep["ok"] is False        # 核对没跑完，不能声称一致


def test_repair_restores_missing_vectors(env):
    """修复：把缺失的知识块重新向量化写回，修复后自检通过。"""
    db, store, emb = env
    _, rows, col = _add_doc(db, store, emb, n=4, indexed=1)
    assert verify_consistency(db, vector_store=store)["ok"] is False

    res = repair_consistency(db, vector_store=store, embedder=emb)
    assert res["repaired_chunks"] == 3
    assert res["before"]["n_missing"] == 3
    assert res["after"]["n_missing"] == 0
    assert res["ok"] is True
    assert store.list_ids(col) == {c.id for c in rows}


def test_repair_is_idempotent(env):
    """修复应幂等：一致时再修一次不动任何数据。"""
    db, store, emb = env
    _add_doc(db, store, emb, n=2)
    res = repair_consistency(db, vector_store=store, embedder=emb)
    assert res["repaired_chunks"] == 0
    assert res["ok"] is True


def test_repair_skips_locked_collection(env, tmp_path):
    """集合被锁定（载入失败）时不得强行写入，否则会覆盖磁盘上没能载入的旧向量。"""
    db, store, emb = env
    _add_doc(db, store, emb, n=3, indexed=1)
    raw = (tmp_path / "faiss" / f"{PUBLIC_COLLECTION}.index").read_bytes()
    (tmp_path / "faiss" / f"{PUBLIC_COLLECTION}.index").write_bytes(raw[: len(raw) // 2])
    broken = FaissVectorStore(data_dir=tmp_path / "faiss")

    res = repair_consistency(db, vector_store=broken, embedder=emb)
    assert res["repaired_chunks"] == 0
    assert res["skipped"] and res["skipped"][0]["collection"] == PUBLIC_COLLECTION
    assert "拒绝写入" in res["skipped"][0]["reason"] or "锁定" in res["skipped"][0]["reason"]


def test_repair_does_not_delete_orphans(env):
    """修复只补缺失、不删孤立向量（删向量属破坏性操作，需人工确认）。"""
    db, store, emb = env
    _add_doc(db, store, emb, n=2)
    store.upsert(PUBLIC_COLLECTION, ids=["ghost-1"], vectors=[[0.125] * 8],
                 metadatas=[{"chunk_id": "ghost-1"}])
    repair_consistency(db, vector_store=store, embedder=emb)
    assert "ghost-1" in store.list_ids(PUBLIC_COLLECTION)
