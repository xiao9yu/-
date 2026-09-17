# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""向量库抽象：工单17 推荐 Milvus（Lite 本地模式，免 Docker），FAISS 兜底。"""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import settings

logger = logging.getLogger("vector_store")


@dataclass
class SearchHit:
    id: str
    score: float
    metadata: dict


class VectorStore(ABC):
    @abstractmethod
    def create_collection(self, name: str, dim: int) -> None: ...

    @abstractmethod
    def upsert(self, name: str, ids: list[str], vectors: list[list[float]], metadatas: list[dict]) -> None: ...

    @abstractmethod
    def search(self, name: str, query_vector: list[float], top_k: int, filter_dict: dict | None = None) -> list[SearchHit]: ...

    @abstractmethod
    def delete(self, name: str, ids: list[str]) -> None: ...


class FaissVectorStore(VectorStore):
    """FAISS 实现：内积度量（向量需归一化），元数据落 JSON 文件。"""

    def __init__(self, data_dir: Path | str = "./data/faiss"):
        import faiss

        self.faiss = faiss
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.indexes: dict[str, object] = {}
        self.ids: dict[str, list[str]] = {}
        self.metas: dict[str, list[dict]] = {}
        self._load()

    def _paths(self, name):
        return self.data_dir / f"{name}.index", self.data_dir / f"{name}.meta.json"

    def _load(self):
        for idx_file in self.data_dir.glob("*.index"):
            name = idx_file.stem
            meta_file = self.data_dir / f"{name}.meta.json"
            if not meta_file.exists():
                continue
            self.indexes[name] = self.faiss.read_index(str(idx_file))
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            self.ids[name] = data["ids"]
            self.metas[name] = data["metadatas"]

    def _save(self, name):
        idx_file, meta_file = self._paths(name)
        self.faiss.write_index(self.indexes[name], str(idx_file))
        meta_file.write_text(
            json.dumps({"ids": self.ids[name], "metadatas": self.metas[name]}, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_collection(self, name: str, dim: int) -> None:
        if name not in self.indexes:
            self.indexes[name] = self.faiss.IndexFlatIP(dim)
            self.ids[name] = []
            self.metas[name] = []

    def upsert(self, name, ids, vectors, metadatas):
        if name not in self.indexes:
            raise ValueError(f"集合不存在：{name}，请先 create_collection")
        arr = np.array(vectors, dtype="float32")
        self.faiss.normalize_L2(arr)
        # 重复 id 先删除再插入（幂等 upsert）
        for i in ids:
            if i in self.ids[name]:
                pos = self.ids[name].index(i)
                self.indexes[name].remove_ids(np.array([pos], dtype="int64"))
                del self.ids[name][pos]
                del self.metas[name][pos]
        self.indexes[name].add(arr)
        self.ids[name].extend(ids)
        self.metas[name].extend(metadatas)
        self._save(name)

    def search(self, name, query_vector, top_k, filter_dict=None):
        if name not in self.indexes:
            return []
        qv = np.array([query_vector], dtype="float32")
        self.faiss.normalize_L2(qv)
        ntotal = self.indexes[name].ntotal
        if ntotal == 0:
            return []
        # 有过滤条件时先全量排序再过滤，保证与 Milvus（先过滤后排序）语义一致
        k = ntotal if filter_dict else min(top_k, ntotal)
        scores, indices = self.indexes[name].search(qv, k)
        hits = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            # 返回副本，防止调用方改动污染存储
            meta = dict(self.metas[name][idx])
            if filter_dict and any(str(meta.get(kk)) != str(vv) for kk, vv in filter_dict.items()):
                continue
            hits.append(SearchHit(id=self.ids[name][idx], score=float(score), metadata=meta))
        return hits[:top_k]

    def delete(self, name, ids):
        if name not in self.indexes:
            return
        for i in ids:
            if i in self.ids[name]:
                pos = self.ids[name].index(i)
                self.indexes[name].remove_ids(np.array([pos], dtype="int64"))
                del self.ids[name][pos]
                del self.metas[name][pos]
        self._save(name)


class MilvusVectorStore(VectorStore):
    """Milvus Lite 实现：本地文件模式，无需 Docker。动态字段存 metadata。"""

    def __init__(self, uri: str = "./data/milvus.db"):
        from pymilvus import DataType, MilvusClient

        self.client = MilvusClient(uri)
        self.DataType = DataType

    def create_collection(self, name: str, dim: int) -> None:
        if self.client.has_collection(name):
            return
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", self.DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("vector", self.DataType.FLOAT_VECTOR, dim=dim)
        self.client.create_collection(name, schema=schema)
        index_params = self.client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
        self.client.create_index(name, index_params)

    def upsert(self, name, ids, vectors, metadatas):
        data = [{"id": i, "vector": v, **m} for i, v, m in zip(ids, vectors, metadatas)]
        self.client.upsert(collection_name=name, data=data)

    @staticmethod
    def _build_expr(filter_dict):
        if not filter_dict:
            return ""
        parts = []
        for k, v in filter_dict.items():
            sv = str(v).replace('"', '\\"')
            parts.append(f'{k} == "{sv}"')
        return " and ".join(parts)

    def search(self, name, query_vector, top_k, filter_dict=None):
        if not self.client.has_collection(name):
            return []
        res = self.client.search(
            collection_name=name,
            data=[query_vector],
            limit=top_k,
            filter=self._build_expr(filter_dict) or None,
            output_fields=["*"],
        )
        hits = []
        for hit in res[0]:
            entity = hit.get("entity", {}) or {}
            meta = {k: v for k, v in entity.items() if k not in ("id", "vector")}
            hits.append(SearchHit(id=hit["id"], score=float(hit["distance"]), metadata=meta))
        return hits

    def delete(self, name, ids):
        if self.client.has_collection(name):
            self.client.delete(collection_name=name, ids=ids)


def _build_store() -> VectorStore:
    """按配置构建后端实例：Milvus 异常时自动退回 FAISS（同为设计文档推荐方案）。"""
    if settings.vector_backend == "faiss":
        return FaissVectorStore()
    try:
        return MilvusVectorStore(settings.milvus_uri)
    except Exception as exc:  # 本机环境跑不起 Milvus 时兜底
        logger.warning("Milvus 初始化失败，自动退回 FAISS：%s", exc)
        return FaissVectorStore()


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """模块级单例：避免每次调用重读 FAISS 索引/重建 Milvus 客户端（台账 A-1）。"""
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def reset_vector_store() -> None:
    """重置单例（测试用）。"""
    global _store
    _store = None
