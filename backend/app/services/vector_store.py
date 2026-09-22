# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""向量库抽象：工单17 推荐 Milvus（Lite 本地模式，免 Docker），FAISS 兜底。"""
import json
import logging
import os
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


class CollectionLockedError(RuntimeError):
    """集合在磁盘上有数据但本次未能载入，拒绝写入（否则整库覆盖会让旧向量永久丢失）。

    为什么需要这个异常：FAISS 实现把集合常驻内存、每次 upsert 都把整个集合写回磁盘。
    若某次启动没能载入既有集合（元数据缺失/损坏），`create_collection` 会建出一个
    **空集合**，紧接着的一次 upsert 就把空集合+新向量写回磁盘——旧向量永久消失，
    且全程无报错。实测复现见 tests/test_vector_store.py 的
    `test_unloaded_collection_refuses_write_instead_of_clobbering`。
    """


class VectorStore(ABC):
    @abstractmethod
    def create_collection(self, name: str, dim: int) -> None: ...

    @abstractmethod
    def upsert(self, name: str, ids: list[str], vectors: list[list[float]], metadatas: list[dict]) -> None: ...

    @abstractmethod
    def search(self, name: str, query_vector: list[float], top_k: int, filter_dict: dict | None = None) -> list[SearchHit]: ...

    @abstractmethod
    def delete(self, name: str, ids: list[str]) -> None: ...

    def list_ids(self, name: str) -> set[str] | None:
        """列出集合内全部 id；后端无法枚举时返回 None（一致性自检据此标注"不支持"）。

        定义为非抽象方法：新增能力不强制已有实现改动。
        """
        return None

    def list_collections(self) -> set[str] | None:
        """列出已知集合名；后端无法枚举时返回 None。供一致性自检发现 orphan 向量。"""
        return None


class FaissVectorStore(VectorStore):
    """FAISS 实现：内积度量（向量需归一化），元数据落 JSON 文件。

    索引的读写一律走 Python 层字节 IO + ``faiss.serialize_index`` /
    ``deserialize_index``，**不使用** ``faiss.write_index`` / ``read_index``：
    后两者底层的 C++ ``FileIOWriter`` 用窄字符 ``fopen`` 打开文件，在 Windows 上
    无法打开路径含非 ASCII 字符（如中文）的索引文件，会抛
    ``RuntimeError: ... could not open ...``。

    两种方式的磁盘格式完全一致（均以 4 字节 fourcc ``IBxF`` 开头，实测字节相同），
    因此历史索引文件无需迁移即可继续读取。

    写盘安全：落盘走"临时文件 + ``os.replace``"的原子替换。先前直接覆盖写，
    写盘中断会留下截断的 ``.index``，下次启动只记一条 warning 就跳过——用户侧表现为
    "文档突然搜不到了"，无任何告警。
    """

    def __init__(self, data_dir: Path | str = "./data/faiss"):
        import faiss

        self.faiss = faiss
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.indexes: dict[str, object] = {}
        self.ids: dict[str, list[str]] = {}
        self.metas: dict[str, list[dict]] = {}
        # 磁盘上有文件但本次载入失败的集合：名字 → 失败原因。写入前据此拦截覆盖
        self.unloaded: dict[str, str] = {}
        self._load()

    def _paths(self, name):
        return self.data_dir / f"{name}.index", self.data_dir / f"{name}.meta.json"

    def _refuse(self, name: str, idx_file: Path, reason: str) -> None:
        """载入失败 → 锁定该集合并大声报错（绝不能静默跳过，见 CollectionLockedError）。"""
        self.unloaded[name] = reason
        logger.error(
            "集合 %s 载入失败（%s）：已锁定，拒绝后续写入以避免整库覆盖导致向量永久丢失。"
            "文件：%s。修复：找回同名的 .meta.json，或确认可以丢弃后删除该 "
            ".index/.meta.json 再重新入库；也可调用 GET /api/kb/consistency 查看全库一致性。",
            name, reason, idx_file.name,
        )

    def _load(self):
        self.unloaded.clear()
        for idx_file in self.data_dir.glob("*.index"):
            name = idx_file.stem
            meta_file = self.data_dir / f"{name}.meta.json"
            if not meta_file.exists():
                self._refuse(name, idx_file, "元数据文件 .meta.json 缺失")
                continue
            try:
                index = self._read_index(idx_file)
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                ids, metas = data["ids"], data["metadatas"]
            except Exception as exc:  # noqa: BLE001 — 单个索引损坏不应让整个向量库构造失败
                self._refuse(name, idx_file, str(exc))
                continue
            if len(ids) != index.ntotal or len(metas) != index.ntotal:
                self._refuse(name, idx_file, f"元数据条数 ids={len(ids)}/metas={len(metas)} "
                                             f"与索引 ntotal={index.ntotal} 不一致")
                continue
            self.indexes[name] = index
            self.ids[name] = ids
            self.metas[name] = metas

    def _read_index(self, idx_file: Path):
        """从磁盘读回索引（Python 层读字节，避开 C++ 窄字符 fopen 的路径限制）。"""
        return self.faiss.deserialize_index(np.frombuffer(idx_file.read_bytes(), dtype="uint8"))

    def _write_index(self, idx_file: Path, index) -> None:
        """把索引落盘（Python 层写字节，理由同上）。"""
        self._atomic_write(idx_file, self.faiss.serialize_index(index).tobytes())

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        """原子替换写：先写同目录临时文件再 rename，避免中断留下截断文件。

        必须同目录（跨盘 rename 非原子）；``os.replace`` 在 POSIX 与 NTFS 上均为原子替换。
        """
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def _check_writable(self, name: str) -> None:
        """写入前置检查：集合被锁定则拒绝（否则会覆盖掉磁盘上没能载入的旧向量）。"""
        if name in self.unloaded:
            raise CollectionLockedError(
                f"集合 {name} 在磁盘上有数据但本次未能载入（{self.unloaded[name]}），"
                f"已拒绝写入以避免覆盖导致向量永久丢失。请先修复该集合的索引/元数据文件。"
            )

    def _save(self, name):
        self._check_writable(name)
        idx_file, meta_file = self._paths(name)
        self._write_index(idx_file, self.indexes[name])
        self._atomic_write(
            meta_file,
            json.dumps({"ids": self.ids[name], "metadatas": self.metas[name]},
                       ensure_ascii=False).encode("utf-8"),
        )

    def list_ids(self, name: str) -> set[str] | None:
        """集合内全部 id。被锁定的集合返回 None（表示"未知"而非"空"）。"""
        if name in self.unloaded:
            return None
        return set(self.ids.get(name, []))

    def list_collections(self) -> set[str] | None:
        """磁盘上存在索引的集合名（含载入失败被锁定的，它们同样占用名字）。"""
        return set(self.ids) | set(self.unloaded)

    def create_collection(self, name: str, dim: int) -> None:
        self._check_writable(name)
        if name not in self.indexes:
            self.indexes[name] = self.faiss.IndexFlatIP(dim)
            self.ids[name] = []
            self.metas[name] = []

    def upsert(self, name, ids, vectors, metadatas):
        # 先判锁定：被锁定的集合即便不在内存索引里，也必须报"拒绝覆盖"而不是"集合不存在"，
        # 否则调用方会以为只是忘了建集合，转而 create_collection 从而覆盖磁盘数据
        self._check_writable(name)
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

    def list_ids(self, name: str) -> set[str] | None:
        """枚举集合内全部 id（分页拉取）。Milvus 查询失败时返回 None，由自检标注"不可用"。"""
        if not self.client.has_collection(name):
            return set()
        try:
            out: set[str] = set()
            offset = 0
            page = 1000
            while True:
                rows = self.client.query(
                    collection_name=name, filter="", output_fields=["id"],
                    limit=page, offset=offset,
                )
                if not rows:
                    break
                out.update(str(r["id"]) for r in rows)
                if len(rows) < page:
                    break
                offset += page
            return out
        except Exception as exc:  # noqa: BLE001 — 自检不可因单集合查询失败而整体失败
            logger.warning("Milvus 集合 %s 枚举 id 失败：%s", name, exc)
            return None

    def list_collections(self) -> set[str] | None:
        try:
            return set(self.client.list_collections())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Milvus 枚举集合失败：%s", exc)
            return None


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
