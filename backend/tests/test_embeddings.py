# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import pytest

from app.services.embeddings import get_embedder


@pytest.mark.smoke
def test_embed_chinese_dim():
    emb = get_embedder()
    vecs = emb.embed_texts(["你好世界"])
    assert len(vecs) == 1
    assert len(vecs[0]) == emb.dim
    assert all(isinstance(x, float) for x in vecs[0])


def test_embedder_load_failure_raises_friendly_error(monkeypatch):
    """模型加载失败抛 EmbedderError 且含镜像指引（台账 B 终审 3）。"""
    import pytest
    from app.services import embeddings

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("offline")
    monkeypatch.setattr(embeddings, "Embedder", Boom)
    monkeypatch.setattr(embeddings, "_embedder", None)
    with pytest.raises(embeddings.EmbedderError, match="HF_ENDPOINT"):
        embeddings.get_embedder()
    monkeypatch.setattr(embeddings, "_embedder", None)


def test_local_cache_ready_true_when_cached(monkeypatch):
    """缓存齐备时返回 True（调用方以 local_files_only 离线加载）。"""
    import huggingface_hub
    from app.services.embeddings import local_cache_ready

    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda repo, f: "/fake/cached")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    assert local_cache_ready("BAAI/bge-m3") is True


def test_local_cache_ready_false_when_not_cached(monkeypatch):
    """缓存缺失时返回 False（首次下载场景走在线路径）。"""
    import huggingface_hub
    from app.services.embeddings import local_cache_ready

    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda repo, f: None)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    assert local_cache_ready("BAAI/bge-m3") is False


def test_local_cache_ready_respects_env_offline(monkeypatch):
    """显式 HF_HUB_OFFLINE=1 时无条件返回 True。"""
    from app.services.embeddings import local_cache_ready

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    assert local_cache_ready("BAAI/bge-m3") is True
