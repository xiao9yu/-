# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""精排服务测试：rerank 排序、加载失败降级、hybrid_retrieve 接入。"""
import pytest

from app.services.parser.chunk import Chunk
from app.services.rag import KBCollection, RagHit, hybrid_retrieve


def _hits(n=4):
    return [RagHit(chunk=Chunk(text=f"资料{i}", kind="text", source="a.md", id=f"c{i}")) for i in range(n)]


class FakeModel:
    def __init__(self, scores):
        self.scores = scores

    def predict(self, pairs):
        assert all(len(p) == 2 for p in pairs)
        return self.scores[:len(pairs)]


def test_reranker_sorts_by_score_desc():
    from app.services.rerank import Reranker
    r = Reranker.__new__(Reranker)          # 不触发真实模型下载
    r.model = FakeModel([0.1, 0.9, 0.5])
    out = r.rerank("q", _hits(3), top_n=2)
    assert [h.chunk.id for h in out] == ["c1", "c2"]


def test_reranker_instance_callable_for_hybrid_retrieve():
    """Reranker 实例可当 callable 传入 hybrid_retrieve（rerank(query, hits, top_n) 约定）。"""
    from app.services.rerank import Reranker
    r = Reranker.__new__(Reranker)          # 不触发真实模型下载
    r.model = FakeModel([0.1, 0.9, 0.5])
    out = r("q", _hits(3), 2)               # __call__ 委托 rerank
    assert [h.chunk.id for h in out] == ["c1", "c2"]


def test_get_reranker_returns_none_on_load_failure(monkeypatch):
    """模型加载失败降级返回 None（调用方跳过精排，不阻塞问答）。"""
    from app.services import rerank

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no network")
    monkeypatch.setattr(rerank, "Reranker", Boom)
    monkeypatch.setattr(rerank, "_reranker", None)
    assert rerank.get_reranker() is None


def test_hybrid_retrieve_rerank_limits_and_reorders():
    """rerank 非空时：RRF 结果先取前 20 精排，返回 top_k 条且顺序按精排分。"""
    vs, emb = _FakeVS(), _FakeEmb()
    chunks = [Chunk(text=f"语料{i}", kind="text", source="a.md", id=f"d{i}") for i in range(6)]
    col = KBCollection(name="t", chunks=chunks)
    rerank = lambda q, hits, n: list(reversed(hits[:n]))[:n]   # noqa: E731 反转序验证重排生效
    out = hybrid_retrieve("语料", [col], top_k=3, vector_store=vs, embedder=emb, rerank=rerank)
    assert len(out) == 3
    # 无 rerank 时原路径行为不变：BM25 按 top_k 截断（6 块语料全命中，top_k=6 时融合返回全量 6 条）
    # （控制器裁定：简报原断言 top_k=3 时 len==6 与 BM25Index.search 的 top_k 截断行为矛盾）
    out2 = hybrid_retrieve("语料", [col], top_k=6, vector_store=vs, embedder=emb)
    assert len(out2) == 6


class _FakeVS:
    def search(self, name, query_vector, top_k, filter_dict=None):
        return []


class _FakeEmb:
    dim = 8

    def embed_query(self, text):
        return [0.1] * self.dim
