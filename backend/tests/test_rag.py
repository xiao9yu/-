# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
from app.services.parser.chunk import Chunk
from app.services.rag import BM25Index, KBCollection, hybrid_retrieve, rrf_fuse, tokenize
from app.services.vector_store import FaissVectorStore, SearchHit


def _chunks():
    return [
        Chunk(text="梯度下降是机器学习最基础的优化算法", kind="text", source="教材.pdf", id="c1"),
        Chunk(text="房价预测案例使用线性回归模型", kind="text", source="笔记.md", id="c2"),
        Chunk(text="计算机网络的七层模型", kind="text", source="教材.pdf", id="c3"),
    ]


def test_tokenize_chinese():
    tokens = tokenize("梯度下降优化算法")
    assert "梯度" in tokens or "梯度下降" in tokens
    assert len(tokens) >= 2


def test_bm25_relevant_first():
    idx = BM25Index(_chunks())
    hits = idx.search("梯度下降是什么", top_k=2)
    assert hits[0].chunk.id == "c1"


def test_rrf_fuse_dedup_and_rank():
    chunks = _chunks()
    list1 = [SearchHit(id="c1", score=0.9, metadata={"chunk_id": "c1"})]
    list2 = [SearchHit(id="c2", score=0.8, metadata={"chunk_id": "c2"})]
    # 转成 RagHit 列表：c1 在两个列表都出现
    a = [type("H", (), {"chunk": chunks[0], "score": 0.9})()]
    b = [type("H", (), {"chunk": chunks[0], "score": 0.8})(), type("H", (), {"chunk": chunks[1], "score": 0.7})()]
    fused = rrf_fuse([a, b])
    assert fused[0].chunk.id == "c1"  # 出现两次融合分更高
    assert len(fused) == 2


def test_hybrid_retrieve_merges_vector_and_bm25(tmp_path):
    class FakeEmbedder:
        def embed_query(self, text):
            # 与 c1 向量相近
            return [1.0, 0.0, 0.0]

    store = FaissVectorStore(data_dir=tmp_path / "faiss")
    store.create_collection("kb", dim=3)
    store.upsert(
        "kb",
        ids=["c1", "c2", "c3"],
        vectors=[[1.0, 0, 0], [0.9, 0.1, 0], [0.0, 1.0, 0]],
        metadatas=[{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c3"}],
    )
    col = KBCollection(name="kb", chunks=_chunks())
    hits = hybrid_retrieve("计算机网络", [col], top_k=2, vector_store=store, embedder=FakeEmbedder())
    ids = [h.chunk.id for h in hits]
    assert "c1" in ids  # 向量命中：查询向量 [1,0,0] 的最近邻
    assert "c3" in ids  # 仅 BM25 可命中：c3 向量与查询向量正交，但文本匹配"计算机网络"


def test_bm25_two_chunk_corpus_has_nonzero_scores():
    """2 块语料 BM25 评分应非 0（台账 A-5：旧 rank-bm25 公式 N=df 时 IDF 恒 0）。"""
    from app.services.parser.chunk import Chunk
    from app.services.rag import BM25Index
    chunks = [Chunk(text="梯度下降是机器学习核心优化算法", kind="text", source="a.md"),
              Chunk(text="线性回归用于回归任务", kind="text", source="b.md")]
    hits = BM25Index(chunks).search("梯度下降")
    assert hits and hits[0].score > 0

def test_get_bm25_index_cached():
    from app.services.parser.chunk import Chunk
    from app.services.rag import get_bm25_index
    chunks = [Chunk(text="缓存测试语料一", kind="text", source="a.md"),
              Chunk(text="缓存测试语料二", kind="text", source="b.md")]
    assert get_bm25_index(chunks) is get_bm25_index(chunks)
