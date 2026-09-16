# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""课程资源检索：上传课程资源 → 实时解析 → 关键词+向量混合检索 → 引用标注。
实现策略：每次搜索实时解析课程全部资源文件（演示规模文件少，源文件即真相、无状态、
重启安全），构建临时 FAISS 索引 + BM25，复用底座 hybrid_retrieve（RRF 融合）。
"""
import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..models.prep import CourseFile
from ..services.embeddings import get_embedder
from ..services.file_service import get_file_path, save_upload
from ..services.parser import parse_document
from ..services.rag import KBCollection, hybrid_retrieve
from ..services.vector_store import FaissVectorStore


class _StableStore:
    """包装向量库：同分命中按插入顺序稳定排序。
    FAISS 对同分命中的返回顺序不稳定（多线程堆排序），会随机影响 RRF 排名；
    稳定为文档解析顺序后结果可复现。真实 embedding 下向量分几乎不会同分，
    该包装只影响同分兜底路径，不影响正常检索语义。
    """

    def __init__(self, inner, order: dict[str, int]):
        self._inner = inner
        self._order = order

    def search(self, name, query_vector, top_k, filter_dict=None):
        hits = self._inner.search(name, query_vector, top_k, filter_dict=filter_dict)
        return sorted(hits, key=lambda h: (-h.score, self._order.get(h.id, 0)))


def add_resource(course_id: int, file: UploadFile, upload_dir: Path | str, db: Session):
    """上传课程资源文件：底座落盘 + course_files 登记。owner_id 记 0（课程资源不属个人）。"""
    record = save_upload(file, owner_id=0, upload_dir=upload_dir, db=db)
    db.add(CourseFile(course_id=course_id, file_id=record.id))
    db.commit()
    return record


def list_resources(course_id: int, db: Session):
    """课程资源文件列表。"""
    from ..models.file import FileRecord
    links = db.query(CourseFile).filter(CourseFile.course_id == course_id).all()
    records = [db.get(FileRecord, link.file_id) for link in links]
    return [r for r in records if r is not None]


def search_resources(course_id: int, query: str, upload_dir: Path | str, db: Session,
                     top_k: int = 5, *, vector_store=None, embedder=None) -> list[dict]:
    """混合检索课程资源，返回 [{chunk, score, ref}]；ref 为引用标注文本。"""
    resources = list_resources(course_id, db)
    if not resources:
        return []
    chunks = []
    for record in resources:
        path = get_file_path(record, upload_dir)
        if path.exists():
            # 解析器 source 记磁盘名（uuid），引用标注需用用户上传时的原始文件名
            parsed = parse_document(path)
            for c in parsed:
                c.source = record.filename
            chunks.extend(parsed)
    if not chunks:
        return []
    emb = embedder or get_embedder()
    # 临时向量索引：每次搜索重建（演示规模 chunk 数少，内积索引构建为毫秒级）
    with tempfile.TemporaryDirectory(prefix="prep_search_") as tmp:
        store = vector_store or FaissVectorStore(data_dir=tmp)
        store.create_collection("course_res", dim=emb.dim)
        store.upsert(
            "course_res",
            ids=[c.id for c in chunks],
            vectors=emb.embed_texts([c.text for c in chunks]),
            metadatas=[{"chunk_id": c.id, "source": c.source, "page": c.page} for c in chunks],
        )
        collection = KBCollection(name="course_res", chunks=chunks)
        # 自建临时索引时包装稳定同分排序；调用方显式传入的 vector_store 保持原样
        order = {c.id: i for i, c in enumerate(chunks)}
        vs = store if vector_store is not None else _StableStore(store, order)
        hits = hybrid_retrieve(query, [collection], top_k=top_k,
                               vector_store=vs, embedder=emb)
    return [
        {
            "chunk": h.chunk,
            "score": round(h.score, 4),
            "ref": _format_ref(i, h.chunk),
        }
        for i, h in enumerate(hits, start=1)
    ]


def _format_ref(ref_no: int, chunk) -> str:
    """引用标注：[N] 来源：文件名 第X页（页为空时省略）。"""
    page = f" 第{chunk.page}页" if chunk.page is not None else ""
    return f"[{ref_no}] 来源：{chunk.source}{page}"
