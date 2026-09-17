# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""精排服务：bge-reranker 对 RRF 粗排结果重打分（设计文档 §4.2.2 重排序要求）。"""
import logging

from .rag import RagHit

logger = logging.getLogger("rerank")


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, hits: list[RagHit], top_n: int = 5) -> list[RagHit]:
        """逐对打分（query, chunk.text）→ 按分降序取 top_n。"""
        if not hits:
            return []
        scores = self.model.predict([[query, h.chunk.text] for h in hits])
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [hits[i] for i in order[:top_n]]


_reranker = None


def get_reranker() -> Reranker | None:
    """懒加载单例；模型加载失败返回 None（调用方降级跳过精排，问答不阻塞）。"""
    global _reranker
    if _reranker is None:
        try:
            _reranker = Reranker()
        except Exception as exc:
            logger.warning("bge-reranker 加载失败，降级跳过精排：%s", exc)
            _reranker = False
    return _reranker or None
