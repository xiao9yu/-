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
