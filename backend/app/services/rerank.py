# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""精排服务：bge-reranker 对 RRF 粗排结果重打分（设计文档 §4.2.2 重排序要求）。"""
import logging
import threading

from .embeddings import local_cache_ready
from .rag import RagHit

logger = logging.getLogger("rerank")


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        # 缓存齐备时离线加载，避免 HF 网络重试拖慢首问（modules.json 缺失会自动
        # 降级为 transformers 路径，本地 config.json+权重齐备即可加载）
        local = local_cache_ready(model_name)
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, local_files_only=local)

    def rerank(self, query: str, hits: list[RagHit], top_n: int = 5) -> list[RagHit]:
        """逐对打分（query, chunk.text）→ 按分降序取 top_n。"""
        if not hits:
            return []
        scores = self.model.predict([[query, h.chunk.text] for h in hits])
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [hits[i] for i in order[:top_n]]

    def __call__(self, query: str, hits: list[RagHit], top_n: int = 5) -> list[RagHit]:
        """兼容 hybrid_retrieve 的 callable 约定（rerank(query, hits, top_n)）。

        hybrid_retrieve 把 rerank 参数当可调用对象使用，而 get_reranker 返回
        Reranker 实例；不加 __call__ 则问答路由在生产（模型加载成功）时抛
        TypeError 中断 SSE 流。
        """
        return self.rerank(query, hits, top_n)


_reranker = None
_lock = threading.Lock()


def get_reranker() -> Reranker | None:
    """懒加载单例；模型加载失败返回 None（调用方降级跳过精排，问答不阻塞）。

    终审修复：并发锁防重入——预热线程（main.lifespan 启动时后台加载）持锁期间，
    并发请求不排队等待（非阻塞获取），直接返回 None 降级为仅 RRF 融合；
    避免请求线程阻塞在 CrossEncoder 下载/读盘上，也杜绝模型被并发二次构建。
    获锁后双重检查哨兵，预热期间被其他线程抢先加载完成时直接复用。
    """
    global _reranker
    if _reranker is None:
        if _lock.acquire(blocking=False):
            try:
                if _reranker is None:  # 双重检查：获锁前可能已被预热线程加载完成
                    try:
                        _reranker = Reranker()
                    except Exception as exc:
                        logger.warning("bge-reranker 加载失败，降级跳过精排：%s", exc)
                        _reranker = False
            finally:
                _lock.release()
    return _reranker or None
