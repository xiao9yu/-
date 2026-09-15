# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import pytest

from app.services.vector_store import FaissVectorStore, get_vector_store


@pytest.fixture
def store(tmp_path):
    return FaissVectorStore(data_dir=tmp_path / "faiss")


def _seed(store):
    store.create_collection("kb1", dim=3)
    store.upsert(
        "kb1",
        ids=["a", "b"],
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        metadatas=[{"chunk_id": "c-a", "source": "x.pdf"}, {"chunk_id": "c-b", "source": "y.pdf"}],
    )


def test_upsert_and_search(store):
    _seed(store)
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].metadata["chunk_id"] == "c-a"
    assert hits[0].score >= hits[1].score


def test_search_with_filter(store):
    _seed(store)
    hits = store.search("kb1", [0.7, 0.7, 0.0], top_k=2, filter_dict={"source": "y.pdf"})
    assert len(hits) == 1
    assert hits[0].id == "b"


def test_delete_removes(store):
    _seed(store)
    store.delete("kb1", ["a"])
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert all(h.id != "a" for h in hits)


def test_factory_faiss_backend(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "vector_backend", "faiss")
    store = get_vector_store()
    assert isinstance(store, FaissVectorStore)


@pytest.mark.smoke
def test_milvus_lite_smoke(tmp_path):
    """Milvus Lite 冒烟：本机跑不起来时此测试可跳过（FAISS 兜底）。"""
    milvus = pytest.importorskip("pymilvus")
    from app.services.vector_store import MilvusVectorStore
    uri = str(tmp_path / "milvus.db")
    store = MilvusVectorStore(uri=uri)
    store.create_collection("kb1", dim=3)
    store.upsert(
        "kb1", ids=["a"],
        vectors=[[1.0, 0.0, 0.0]],
        metadatas=[{"chunk_id": "c-a", "source": "x.pdf"}],
    )
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=1)
    assert hits[0].id == "a"
