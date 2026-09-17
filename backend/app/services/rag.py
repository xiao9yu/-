# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 检索核心：BM25 关键词 + 向量检索混合，RRF 融合重排序。
工单18「混合检索→重排序→最优结果」的算法实现；工单17 资源检索复用。
"""
from dataclasses import dataclass, field

import jieba
from rank_bm25 import BM25Plus

from .embeddings import get_embedder
from .parser.chunk import Chunk
from .vector_store import get_vector_store


def tokenize(text: str) -> list[str]:
    """中文分词（搜索引擎模式，利于短查询召回）。"""
    return [t for t in jieba.lcut_for_search(text) if t.strip()]


@dataclass
class RagHit:
    chunk: Chunk
    score: float = 0.0


@dataclass
class KBCollection:
    """一次检索涉及的集合：向量集合名 + 对应语料（供 BM25 与 chunk 回查）。"""
    name: str
    chunks: list[Chunk]
    filter_dict: dict | None = None  # 私有库过滤，如 {"owner_id": "3"}


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        # 旧公式（BM25Okapi）N=df 时 IDF 恒 0，2 块语料下任何查询都召回为空；
        # Plus 公式 IDF=ln((N+1)/df) 规避该问题（台账 A-5，控制器裁定）。
        self._bm25 = BM25Plus([tokenize(c.text) for c in chunks]) if chunks else None

    def search(self, query: str, top_k: int = 10) -> list[RagHit]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [RagHit(chunk=self.chunks[i], score=float(scores[i])) for i in order if scores[i] > 0]


def rrf_fuse(ranked_lists: list[list[RagHit]], k: int = 60) -> list[RagHit]:
    """RRF 融合：同一 chunk 在多个排序列表中得分累加（1/(k+rank+1)），按融合分降序。"""
    fused: dict[str, tuple[RagHit, float]] = {}
    for hits in ranked_lists:
        for rank, h in enumerate(hits):
            s = 1.0 / (k + rank + 1)
            if h.chunk.id in fused:
                fused[h.chunk.id] = (fused[h.chunk.id][0], fused[h.chunk.id][1] + s)
            else:
                fused[h.chunk.id] = (h, s)
    return [h for h, _ in sorted(fused.values(), key=lambda x: -x[1])]


_bm25_cache: dict[tuple[str, ...], BM25Index] = {}


def get_bm25_index(chunks: list[Chunk]) -> BM25Index:
    """按语料指纹缓存 BM25 索引（台账 A-5：每查询重建浪费）；缓存上限 8 个，超限整体清空。"""
    key = tuple(c.id for c in chunks)
    if key not in _bm25_cache:
        if len(_bm25_cache) >= 8:
            _bm25_cache.clear()
        _bm25_cache[key] = BM25Index(chunks)
    return _bm25_cache[key]


def hybrid_retrieve(
    question: str,
    collections: list[KBCollection],
    top_k: int = 5,
    *,
    vector_store=None,
    embedder=None,
    rerank=None,
) -> list[RagHit]:
    """混合检索：每个集合各做向量检索 + BM25，全部结果 RRF 融合。
    rerank 非空时：RRF 粗排取前 20 → 精排回 top_k（工单18 重排序链路）。"""
    vs = vector_store or get_vector_store()
    emb = embedder or get_embedder()
    qv = emb.embed_query(question)
    ranked: list[list[RagHit]] = []
    for col in collections:
        by_id = {c.id: c for c in col.chunks}
        vhits = []
        for hit in vs.search(col.name, qv, top_k, filter_dict=col.filter_dict):
            chunk = by_id.get(hit.metadata.get("chunk_id"))
            if chunk is not None:
                vhits.append(RagHit(chunk=chunk, score=float(hit.score)))
        bhits = get_bm25_index(col.chunks).search(question, top_k)
        ranked.append(vhits)
        ranked.append(bhits)
    fused = rrf_fuse(ranked)
    if rerank is not None:
        return rerank(question, fused[:20], top_k)
    return fused
