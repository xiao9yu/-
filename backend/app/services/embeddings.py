# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""Embedding 服务：本地 bge-m3（DeepSeek 无 embedding API，本地免费离线）。"""
import threading

from ..config import settings


class Embedder:
    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or settings.embedding_model
        self.model = SentenceTransformer(self.model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（bge-m3 输出已归一化，配合 COSINE 度量）。"""
        if not texts:
            return []
        vecs = self.model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


_embedder: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = Embedder()
        return _embedder
