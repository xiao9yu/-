# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""精排服务：bge-reranker 对 RRF 粗排结果重打分（设计文档 §4.2.2 重排序要求）。

transformers 直载（不用 sentence-transformers 的 CrossEncoder）：本机 HF 不可达时，
CrossEncoder 经 AutoProcessor 加载，即使 local_files_only=True 也会对未缓存的
preprocessor_config.json 等文件逐文件网络探测重试 → 预热线程失败 → get_reranker
缓存 False 哨兵 → 全部问答静默降级为仅 RRF 融合，无关文档的低分块填满 top_k、
引用溯源撒到所有文件。直载纯文本路径（tokenizer + 分类头）缓存齐备时完全离线。
"""
import logging
import math
import threading

from ..config import settings
from .embeddings import local_cache_ready
from .rag import RagHit

logger = logging.getLogger("rerank")

_ABS_FLOOR = 0.35   # 相关度绝对下限（sigmoid 后）：低于此分的块视为不相关，不引用
_REL_RATIO = 0.5    # 相对下限：低于本问最高分一半的块视为不相关
_DEFAULT_MAX_LEN = 1024     # 截断长度兜底：chunk 800 字 + 问句，XLM-R 中文约 0.65 token/字


def _max_len() -> int:
    """截断长度取配置（settings.rerank_max_len），便于用 A/B 脚本对照不同档位。

    注意：调小该值**会截断 chunk 尾部**，从而改变精排分数与阈值过滤结果，属质量-时延
    权衡，不是纯性能开关。改动前请先用 backend/eval/rerank_ab.py 做对照。
    """
    return int(getattr(settings, "rerank_max_len", _DEFAULT_MAX_LEN))


def _sigmoid(x: float) -> float:
    """防溢出 sigmoid（math.exp 对 |x|>709 抛 OverflowError）。"""
    x = max(-100.0, min(100.0, x))
    return 1.0 / (1.0 + math.exp(-x))


class _TransformerRerankModel:
    """transformers 直载模型，对外提供 CrossEncoder 式 predict(pairs) 接口（测试 seam）。"""

    def __init__(self, model_name: str, local_files_only: bool):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name, local_files_only=local_files_only
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_name, local_files_only=local_files_only
        )
        self._model.eval()

    def predict(self, pairs: list[tuple[str, str]], max_length: int | None = None) -> list[float]:
        """逐对打原始 logits（调用方 sigmoid 成相关度；兼容 CrossEncoder.predict 约定）。

        max_length 显式传入时覆盖配置——供 A/B 脚本在同一进程内对照不同截断档位。
        """
        import torch

        enc = self._tokenizer(
            pairs, padding=True, truncation=True,
            max_length=max_length or _max_len(), return_tensors="pt",
        )
        with torch.no_grad():
            logits = self._model(**enc).logits[:, 0]
        return logits.tolist()


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        # 缓存齐备时离线加载，避免 HF 网络重试拖慢首问
        local = local_cache_ready(model_name)
        self.model = _TransformerRerankModel(model_name, local_files_only=local)

    def rerank(self, query: str, hits: list[RagHit], top_n: int = 5) -> list[RagHit]:
        """逐对打分 → sigmoid 相关度 → 阈值过滤弱命中 → 按分降序取 top_n。

        阈值过滤是引用溯源不越界的保障：无关文档的块即使被 RRF 粗排混入，
        得分也低，在此被丢弃；否则 top_k 恒被填满、引用标签散落所有文件。
        """
        if not hits:
            return []
        logits = self.model.predict([[query, h.chunk.text] for h in hits])
        scores = [_sigmoid(x) for x in logits]
        floor = max(_ABS_FLOOR, _REL_RATIO * max(scores))
        kept: list[tuple[float, RagHit]] = []
        for s, h in zip(scores, hits):
            h.score = s  # 写回相关度分，供下游观测
            if s >= floor:
                kept.append((s, h))
        kept.sort(key=lambda t: -t[0])
        return [h for _, h in kept[:top_n]]

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
    避免请求线程阻塞在模型下载/读盘上，也杜绝模型被并发二次构建。
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
