# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import json

import numpy as np
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


def test_get_vector_store_singleton(monkeypatch):
    """get_vector_store 应返回模块级单例（台账 A-1：避免每次重读 FAISS 索引）。"""
    from app.services import vector_store as vs

    calls = []
    class FakeStore:
        def __init__(self): calls.append(1)
    monkeypatch.setattr(vs, "_build_store", lambda: FakeStore())
    vs.reset_vector_store()
    s1 = vs.get_vector_store()
    s2 = vs.get_vector_store()
    assert s1 is s2
    assert len(calls) == 1
    vs.reset_vector_store()
    s3 = vs.get_vector_store()
    assert s3 is not s1          # reset 后重建
    assert len(calls) == 2
    vs.reset_vector_store()


# ---------------------------------------------------------------------------
# 回归：FAISS 与含非 ASCII 字符的路径
# ---------------------------------------------------------------------------

def _require_ascii_path(path, why: str) -> None:
    """旧版 faiss.write_index 本身就不支持非 ASCII 路径，兼容用例需在 ASCII 目录下跑。"""
    if not str(path).isascii():
        pytest.skip(f"当前临时目录含非 ASCII 字符，无法用于{why}：{path}")


def test_faiss_roundtrip_under_non_ascii_path(tmp_path):
    """回归：路径含中文时 FAISS 索引仍可正常落盘与读回。

    旧实现用 faiss.write_index/read_index，其 C++ FileIOWriter 用窄字符 fopen，
    Windows 下打不开含非 ASCII 字符的绝对路径，upsert 会直接抛
    `RuntimeError: ... could not open ...`。改为 Python 层字节 IO 后应正常。
    """
    data_dir = tmp_path / "中文知识库" / "faiss"
    store = FaissVectorStore(data_dir=data_dir)
    _seed(store)
    assert (data_dir / "kb1.index").exists(), "索引未落盘"

    # 关键：重新构造实例从磁盘读回，证明落盘真的可用而非只留在内存
    reopened = FaissVectorStore(data_dir=data_dir)
    assert "kb1" in reopened.indexes
    hits = reopened.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert [h.id for h in hits] == ["a", "b"]
    assert hits[0].metadata["chunk_id"] == "c-a"


def test_faiss_reads_legacy_index_written_by_write_index(tmp_path):
    """向后兼容：旧版本用 faiss.write_index 落盘的索引必须仍能读出来。

    write_index 与 serialize_index 的产物字节一致（均以 fourcc IBxF 开头），
    本用例把这一事实钉死，防止日后改格式导致既有索引读不出来。
    """
    _require_ascii_path(tmp_path, "写入旧格式索引")
    import faiss as real_faiss

    data_dir = tmp_path / "faiss"
    data_dir.mkdir(parents=True, exist_ok=True)

    legacy = real_faiss.IndexFlatIP(3)
    vecs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype="float32")
    real_faiss.normalize_L2(vecs)
    legacy.add(vecs)
    real_faiss.write_index(legacy, str(data_dir / "kb1.index"))   # 旧版写法
    (data_dir / "kb1.meta.json").write_text(
        json.dumps(
            {
                "ids": ["a", "b"],
                "metadatas": [{"chunk_id": "c-a", "source": "x.pdf"}, {"chunk_id": "c-b", "source": "y.pdf"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = FaissVectorStore(data_dir=data_dir)
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert [h.id for h in hits] == ["a", "b"]
    assert hits[0].metadata["source"] == "x.pdf"


def test_faiss_load_tolerates_corrupt_index(tmp_path):
    """单个索引文件损坏（如写盘中断留下 0 字节）不应让整个向量库构造失败。"""
    data_dir = tmp_path / "faiss"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "broken.index").write_bytes(b"")                 # 0 字节
    (data_dir / "broken.meta.json").write_text(
        json.dumps({"ids": [], "metadatas": []}), encoding="utf-8"
    )
    _seed(FaissVectorStore(data_dir=data_dir))                   # 正常集合应照常工作

    store = FaissVectorStore(data_dir=data_dir)                  # 不应抛异常
    assert "broken" not in store.indexes
    assert "kb1" in store.indexes
    assert store.search("kb1", [1.0, 0.0, 0.0], top_k=1)[0].id == "a"
