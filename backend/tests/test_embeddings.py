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
