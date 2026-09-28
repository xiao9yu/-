# 探针：单题在两档 max_len 下的精排分与 chunk 文本位置（§4.2 残留风险销号归因用，2026-09-28）
# 与生产/评测一致：top_k=5 候选池；用法：python -m eval.probe_rag04（硬编码 rag-04 / student）
import math

from app.db import SessionLocal
from app.models.user import User
from app.services import kb_service
from app.services.embeddings import get_embedder
from app.services.rag import hybrid_retrieve
from app.services.rerank import get_reranker
from app.services.vector_store import get_vector_store

Q = "RAG 的检索环节有哪些常见的优化手段？"

db = SessionLocal()
user = db.query(User).filter(User.username == "student").first()
collections = kb_service._load_collections(user, db)
embedder = get_embedder()
store = get_vector_store()
reranker = get_reranker()

pool = hybrid_retrieve(Q, collections, top_k=5,
                       vector_store=store, embedder=embedder, rerank=None)
print(f"候选池 {len(pool)} 条\n")
sig = lambda x: 1 / (1 + math.exp(-x))
for i, h in enumerate(pool, 1):
    txt = h.chunk.text
    pos = txt.find("检索")
    s384 = reranker.model.predict([[Q, txt[:384]]])[0]
    s1024 = reranker.model.predict([[Q, txt]])[0]
    print(f"[{i}] {h.chunk.source.split('/')[-1][:46]}  len={len(txt)}  首次出现'检索'@{pos}  0..384 含'优化'={('优化' in txt[:384])}")
    print(f"    分(384)={sig(s384):.4f}  分(1024)={sig(s1024):.4f}")
    print(f"    前384: {txt[:120].strip().replace(chr(10), ' ')}")
    if pos >= 0:
        print(f"    检索上下文: ...{txt[max(0, pos-60):pos+140].strip().replace(chr(10), ' ')}...")
    print()
