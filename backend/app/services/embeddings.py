# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""Embedding 服务：本地 bge-m3（DeepSeek 无 embedding API，本地免费离线）。"""
import os
import threading

from ..config import settings


def _force_offline() -> None:
    """进程级强制离线（缓存齐备时调用）。

    环境变量方案无效：huggingface_hub/transformers 的离线标志在各自模块导入时
    从环境变量固化，之后再设环境变量不生效。但 huggingface_hub 的请求层在每次
    请求时动态读取 constants.HF_HUB_OFFLINE（utils/_http.py），transformers 的
    is_offline_mode() 动态读取模块全局 _is_offline_mode——直接改写两者即全程生效，
    不受导入顺序影响。
    """
    try:
        import huggingface_hub.constants as hc
        hc.HF_HUB_OFFLINE = True
    except Exception:
        pass
    try:
        import transformers.utils.hub as th
        th._is_offline_mode = True
    except Exception:
        pass


def local_cache_ready(model_name: str) -> bool:
    """本地缓存齐备时返回 True 并强制进程离线，调用方以 local_files_only=True 加载。

    本机 huggingface.co 不可达：默认加载即使模型已完整缓存，仍对每个配置文件
    （含未缓存的 processor_config 等可选文件）做 10s 超时 × 5 次重试的网络探测，
    首个上传/问答会阻塞数分钟（前端 30s 超时表现为"上传失败"）。
    缓存缺失（首次下载场景）返回 False 走在线路径；缓存残缺时离线加载会快速失败，
    由 EmbedderError 附镜像下载指引。
    """
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        _force_offline()
        return True
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    for probe in ("config_sentence_transformers.json", "config.json", "modules.json"):
        try:
            if try_to_load_from_cache(model_name, probe) is not None:
                _force_offline()
                return True
        except Exception:
            continue  # 探测异常：保守走在线路径
    return False


class Embedder:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.embedding_model
        local = local_cache_ready(self.model_name)
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_name, local_files_only=local)
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


class EmbedderError(Exception):
    """嵌入模型加载失败（含用户可操作的指引）。"""


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            try:
                _embedder = Embedder()
            except Exception as exc:
                raise EmbedderError(
                    f"嵌入模型加载失败：{exc}。首次运行需联网下载 bge-m3"
                    "（可设置 HF_ENDPOINT=https://hf-mirror.com 加速），"
                    "已有模型缓存时可设置 HF_HUB_OFFLINE=1 离线加载。"
                ) from exc
        return _embedder
