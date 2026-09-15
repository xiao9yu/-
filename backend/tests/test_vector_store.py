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


def test_search_filter_returns_top_k_matches_beyond_nearest_neighbors(store):
    """修复回归：过滤应在排序后仍返回满 top_k（而非先取近邻后过滤致空）。"""
    store.create_collection("kb2", dim=3)
    store.upsert(
        "kb2",
        ids=["a", "b", "c", "d"],
        vectors=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0], [0.0, 0.9, 0.1]],
        metadatas=[
            {"chunk_id": "c-a", "source": "x.pdf"},
            {"chunk_id": "c-b", "source": "x.pdf"},
            {"chunk_id": "c-c", "source": "y.pdf"},
            {"chunk_id": "c-d", "source": "y.pdf"},
        ],
    )
    # 查询向量最接近 c/d（y.pdf），但过滤要求 x.pdf：修复前近邻全被过滤 → 空；修复后应返回 a/b
    hits = store.search("kb2", [0.0, 1.0, 0.0], top_k=2, filter_dict={"source": "x.pdf"})
    assert len(hits) == 2
    assert all(h.metadata["source"] == "x.pdf" for h in hits)


def test_search_returns_metadata_copy(store):
    """修复回归：返回的 metadata 是副本，调用方改动不污染存储。"""
    _seed(store)
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    hits[0].metadata["chunk_id"] = "hacked"
    hits2 = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert hits2[0].metadata["chunk_id"] == "c-a"


def test_milvus_expr_escapes_quotes():
    """修复回归：过滤值中的双引号被转义，不能注入 and/or 绕过过滤。"""
    from app.services.vector_store import MilvusVectorStore

    expr = MilvusVectorStore._build_expr({"source": 'x" or 1==1 or "'})
    assert expr == 'source == "x\\" or 1==1 or \\""'
    assert MilvusVectorStore._build_expr({"a": "1", "b": "2"}) == 'a == "1" and b == "2"'
