# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库服务：文档上传 → 多模态解析 → 分块 → 向量化入库 → 列表/删除。

集合约定：公共库 kb_public（admin 维护），私有库 kb_user_{user_id}（每用户一个）。
入库持久化：文档块落 kb_chunks 表，向量落向量库集合（Milvus/FAISS，Task 1 单例）。
"""
import json
import logging
import re
from typing import Any, Iterator

from fastapi import UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.file import FileRecord
from ..models.kb import KbChunk, KbDocument
from ..models.user import Role, User
from ..services.embeddings import EmbedderError, get_embedder
from ..services.file_service import delete_file, get_file_path, save_upload
from ..services.llm_gateway import LLMError, get_gateway
from ..services.parser import parse_document
from ..services.parser.chunk import Chunk
from ..services.rag import KBCollection, hybrid_retrieve
from ..services.rag_ask import _select_hits, build_answer_prompt
from ..services.vector_store import CollectionLockedError, VectorStore, get_vector_store
from . import chat_service, learn_profile

PUBLIC_COLLECTION = "kb_public"

logger = logging.getLogger("kb_service")


def private_collection(user_id: int) -> str:
    """私有库集合名（每用户一个）。"""
    return f"kb_user_{user_id}"


def _collection(doc: KbDocument) -> str:
    return PUBLIC_COLLECTION if doc.scope == "public" else private_collection(doc.owner_id)


def add_document(file: UploadFile, scope: str, user: User, upload_dir, db: Session,
                 *, vector_store: VectorStore | None = None, embedder=None) -> KbDocument:
    """上传文档入库：底座落盘 → 登记 → 解析分块 → 向量化入集合 → 块落表。

    解析为空（含 .doc/.ppt/.xls 二进制老格式）拒绝上传并回滚；
    向量化失败（bge-m3 不可用）保留文档记录 status=failed，EmbedderError 上抛由路由转 502；
    其他未预期异常（向量库故障/解析崩溃）同样记 failed 后上抛（不产生"ready 但 0 块"幻影文档）。
    """
    if scope not in ("public", "private"):
        raise BizError(400, "scope 仅支持 public（公共库）或 private（私有库）")
    if scope == "public" and user.role != Role.admin:
        raise BizError(403, "仅管理员可向公共库上传文档")
    record = save_upload(file, owner_id=user.id, upload_dir=upload_dir, db=db)
    doc = KbDocument(title=record.filename, file_id=record.id, scope=scope, owner_id=user.id)
    # 先记 failed 再提交：索引成功后 _index_document 才置 ready，防止中途异常/崩溃留下幻影 ready 文档
    doc.status = "failed"
    db.add(doc)
    db.commit()
    db.refresh(doc)
    try:
        _index_document(doc, record, upload_dir, db, vector_store=vector_store, embedder=embedder)
    except BizError:
        # 解析为空：整体回滚（文档记录 + 底座文件 + 磁盘）
        db.delete(doc)
        db.commit()
        delete_file(record.id, upload_dir, db)
        raise
    except EmbedderError as exc:
        doc.status = "failed"
        doc.error = str(exc)
        db.commit()
        raise
    except Exception as exc:
        # 其他异常（向量库故障/解析崩溃/提交失败）记 failed 后上抛（复审修复：幻影 ready 文档）
        doc.status = "failed"
        doc.error = str(exc)
        db.commit()
        raise
    return doc


def _index_document(doc: KbDocument, record: FileRecord, upload_dir, db: Session,
                    *, vector_store=None, embedder=None) -> None:
    path = get_file_path(record, upload_dir)
    chunks = [c for c in parse_document(path) if c.text.strip()]
    # 空文本块（含 OCR 空图片块）不参与向量化：零向量 normalize 会产 NaN 污染索引
    if not chunks:
        raise BizError(400, "文档解析结果为空：请确认内容为可提取文本，"
                            "或将 .doc/.ppt/.xls 转换为 .docx/.pptx/.xlsx 后上传")
    for c in chunks:
        c.source = record.filename            # 引用标注用原始文件名
        c.meta["file_id"] = record.id
    emb = embedder or get_embedder()
    vs = vector_store or get_vector_store()
    col = _collection(doc)
    vs.create_collection(col, dim=emb.dim)
    vs.upsert(
        col,
        ids=[c.id for c in chunks],
        vectors=emb.embed_texts([c.text for c in chunks]),
        metadatas=[{"chunk_id": c.id, "source": c.source, "page": c.page,
                    "file_id": record.id, "scope": doc.scope} for c in chunks],
    )
    db.add_all([KbChunk(id=c.id, document_id=doc.id, kind=c.kind, text=c.text,
                        source=c.source, page=c.page, meta=c.meta) for c in chunks])
    doc.chunk_count = len(chunks)
    doc.status = "ready"
    db.commit()


def list_documents(user: User, db: Session) -> list[KbDocument]:
    """文档列表：本人私有库 + 全部公共库（他人私有不可见）。"""
    return (db.query(KbDocument)
            .filter(or_(KbDocument.scope == "public", KbDocument.owner_id == user.id))
            .order_by(KbDocument.created_at.desc())
            .all())


def delete_document(doc_id: int, user: User, upload_dir, db: Session,
                    *, vector_store=None) -> None:
    """删除文档：仅 owner 或 admin；公共库文档仅 admin。同步清理向量、块、底座文件与磁盘。"""
    doc = db.get(KbDocument, doc_id)
    if doc is None:
        raise BizError(404, "文档不存在")
    if doc.scope == "public":
        if user.role != Role.admin:
            raise BizError(403, "公共库文档仅管理员可删除")
    elif doc.owner_id != user.id and user.role != Role.admin:
        raise BizError(403, "无权删除他人私有库文档")
    chunks = db.query(KbChunk).filter(KbChunk.document_id == doc_id).all()
    vs = vector_store or get_vector_store()
    vs.delete(_collection(doc), [c.id for c in chunks])
    for c in chunks:
        db.delete(c)
    file_id = doc.file_id
    db.delete(doc)
    db.commit()
    delete_file(file_id, upload_dir, db)


def answer_events(question: str, user: User, db: Session, *,
                  vector_store=None, embedder=None, reranker=None, gateway=None,
                  session=None) -> Iterator[tuple[str, Any]]:
    """问答事件流（(事件名, 数据) 元组）：citations → delta* → done；失败发 error。

    ask_stream 的 SSE 字符串仅是它的薄包装；WS 语音链路（api/voice.py）直接消费本生成器。

    session（ChatSession）非空即多轮模式：
      · 取该会话最近 N 轮上下文喂进提示词（LLM 能理解"它/这个"这类指代）；
      · 检索前用 rewrite_query 把指代型追问与前一轮问题拼接，避免检索必然空手；
      · 流结束后把本轮问答 + 引用落库，引用可随历史回放（"引用延续"）。
    不传 session 则等价于原单轮行为（既有单轮调用与测试契约不变）。
    """
    answer = ""
    try:
        # 经本模块 get_embedder/get_vector_store 显式解析后传入 hybrid_retrieve：
        # 避免 rag 模块内部各自取真实单例——否则本模块的 monkeypatch 对检索路径是死的，
        # 测试会静默打真实 FAISS 单例（维度冲突 → faiss AssertionError，见 Plan C Task 6 Minor #1）
        emb = embedder or get_embedder()
        vs = vector_store or get_vector_store()
        history = chat_service.recent_history(db, session) if session is not None else []
        retrieval_q = chat_service.rewrite_query(question, history)
        hits = hybrid_retrieve(retrieval_q, _load_collections(user, db), top_k=5,
                               vector_store=vs, embedder=emb, rerank=reranker)
        selected = _select_hits(hits, 4000)
        citations = [
            {
                "ref_no": i,
                "source": h.chunk.source,
                "page": h.chunk.page,
                "kind": h.chunk.kind,
                "excerpt": h.chunk.text[:200],
                "text": h.chunk.text,                       # 全文（前端"展开原文"）
                "image_path": h.chunk.meta.get("image_path"),
                "chunk_id": h.chunk.id,
            }
            for i, h in selected
        ]
        yield ("citations", citations)
        gw = gateway or get_gateway()
        for piece in _clean_ref_stream(
                gw.chat_stream(build_answer_prompt(question, hits, history=history)),
                len(citations)):
            answer += piece
            yield ("delta", {"text": piece})
        # 工单19 画像迭代联动：学生提问命中知识点 → 记低权重事件（失败不影响问答流）
        if user.role == Role.student:
            try:
                learn_profile.record_ask_events(user, question, db)
            except Exception:
                logger.exception("画像事件记录失败（问答不受影响）")
        if session is not None and answer.strip():
            try:
                chat_service.append_turn(db, session, question, answer, citations)
            except Exception:
                # 落库失败不回退已生成内容：本轮照常播报，仅丢失历史（下次提问少一轮上下文）
                logger.exception("会话落库失败（本轮问答不受影响）")
        yield ("done", {})
    except EmbedderError as exc:
        yield ("error", {"message": str(exc)})
    except LLMError as exc:
        yield ("error", {"message": str(exc)})
    except BizError as exc:
        yield ("error", {"message": exc.message})
    except Exception:
        # 兜底：向量库检索故障/精排期异常等未预期错误也按协议发 error，不截断流（复审 Important）
        logger.exception("知识库问答流异常")
        yield ("error", {"message": "问答服务异常，请稍后重试"})


def ask_stream(question: str, user: User, db: Session, *,
               vector_store=None, embedder=None, reranker=None, gateway=None,
               session=None) -> Iterator[str]:
    """流式问答（SSE 生成器）：answer_events 的 SSE 字符串包装（既有前端/测试契约不变）。"""

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    for event, data in answer_events(question, user, db,
                                     vector_store=vector_store, embedder=embedder,
                                     reranker=reranker, gateway=gateway,
                                     session=session):
        yield sse(event, data)


_REF_RE = re.compile(r"\[(\d+)\]")


def _strip_invalid_refs(text: str, max_ref: int) -> tuple[str, list[int]]:
    """剔除回答中的越界引用编号（[0] 或超过引用总数），返回清洗后文本与被剔除的编号。

    评测 §5.4：模型若写出越界编号（如只给 5 条引用却标 [7]），前端会展示指向不存在
    资料的溯源链接且无任何环节能发现。范围内编号原样保留（前端依赖它做引用高亮）。
    """
    bad: list[int] = []

    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= max_ref:
            return m.group(0)
        bad.append(n)
        return ""

    return _REF_RE.sub(repl, text), bad


def _clean_ref_stream(pieces: Iterator[str], max_ref: int) -> Iterator[str]:
    """流式引用编号清洗：跨 chunk 边界被拆开的 [n] 由 carry 缓冲拼接后判定。

    尾部形如 "[12"（无右括号）的片段可能是半个编号，留到下一块拼接；
    流结束时残余 carry 不构成完整编号形态，原样放行。
    """
    carry = ""
    for piece in pieces:
        text = carry + piece
        m = re.search(r"\[\d*$", text)
        if m:
            carry = text[m.start():]
            text = text[:m.start()]
        else:
            carry = ""
        cleaned, bad = _strip_invalid_refs(text, max_ref)
        if bad:
            logger.warning("回答引用编号越界，已剔除：%s", bad)
        if cleaned:
            yield cleaned
    if carry:
        cleaned, bad = _strip_invalid_refs(carry, max_ref)
        if bad:
            logger.warning("回答引用编号越界，已剔除：%s", bad)
        if cleaned:
            yield cleaned


def _load_collections(user: User, db: Session) -> list[KBCollection]:
    """检索语料：公共库全部 + 本人私有库（仅 ready 文档，按集合名组装）。"""
    def rows(cond):
        return (db.query(KbChunk).join(KbDocument, KbChunk.document_id == KbDocument.id)
                .filter(cond, KbDocument.status == "ready").all())

    def to_col(name, chunk_rows):
        chunks = [Chunk(text=r.text, kind=r.kind, source=r.source, id=r.id,
                        page=r.page, meta=dict(r.meta or {})) for r in chunk_rows]
        return KBCollection(name=name, chunks=chunks)

    cols = []
    public_rows = rows(KbDocument.scope == "public")
    if public_rows:
        cols.append(to_col(PUBLIC_COLLECTION, public_rows))
    private_rows = rows(and_(KbDocument.scope == "private", KbDocument.owner_id == user.id))
    if private_rows:
        cols.append(to_col(private_collection(user.id), private_rows))
    return cols


# ---------------- 一致性自检与修复（向量库 ↔ kb_chunks） ----------------

def _enumerate_scope(vs, name: str) -> set[str] | None:
    """取集合内全部 id；后端未实现该能力（或为测试替身）时返回 None（= 未知）。"""
    fn = getattr(vs, "list_ids", None)
    return fn(name) if callable(fn) else None


def _enumerate_collections(vs) -> set[str] | None:
    fn = getattr(vs, "list_collections", None)
    return fn() if callable(fn) else None


def verify_consistency(db: Session, *, vector_store: VectorStore | None = None) -> dict:
    """核对「kb_chunks 表」与「向量库」是否一致，返回可读报告。

    为什么需要它：向量库落盘是**整库覆盖写**，任何一次载入缺失、写盘中断或维度不匹配
    都会让已有向量永久消失，而 `kb_documents.status` 仍是 `ready` —— 系统看起来一切正常，
    只有检索悄悄少了一条召回通道（BM25 读 kb_chunks 仍能命中，向量召回则永久失手）。
    本机实测就存在这样一份文档：`人工智能导论知识库.pdf`（3 块，DB ready，向量 0/3），
    且 `seed_demo_data` 的幂等判断（"已有 ready 公共文档就整体跳过"）重跑也修不了。

    检查三类问题：
      · missing —— ready 文档的知识块在 DB 里存在、向量库里没有（**检索质量损失**）；
      · orphan  —— 向量库里有、kb_chunks 表里已无对应行（删除残留）；
      · doc_row —— 文档自身的记账不一致（chunk_count 与实算不符 / ready 但 0 块）。

    参数 vector_store 主要用于测试注入；不传取单例。
    """
    import time as _time

    vs = vector_store or get_vector_store()
    docs = db.query(KbDocument).all()
    chunk_rows = db.query(KbChunk).all()

    by_doc: dict[int, list[KbChunk]] = {}
    for c in chunk_rows:
        by_doc.setdefault(c.document_id, []).append(c)
    all_chunk_ids = {c.id for c in chunk_rows}

    # 期望集合名：所有文档涉及的集合 ∪ 向量库侧实际存在的集合（后者才能发现 orphan）
    names = {_collection(d) for d in docs}
    store_names = _enumerate_collections(vs)
    if store_names:
        names |= set(store_names)

    expected: dict[str, set[str]] = {}
    for d in docs:
        if d.status != "ready":
            continue
        ids = {c.id for c in by_doc.get(d.id, [])}
        if ids:
            expected.setdefault(_collection(d), set()).update(ids)

    store_ids: dict[str, set[str] | None] = {n: _enumerate_scope(vs, n) for n in sorted(names)}
    unsupported = sorted(n for n, v in store_ids.items() if v is None)

    collections = []
    for n in sorted(names):
        have = store_ids.get(n)
        exp = expected.get(n, set())
        miss = None if have is None else sorted(exp - have)
        orph = None if have is None else sorted(have - all_chunk_ids)
        collections.append({
            "name": n,
            "expected": len(exp),
            "in_store": None if have is None else len(have),
            "missing": None if miss is None else len(miss),
            "orphan": None if orph is None else len(orph),
            "missing_ids": miss or [],
            "orphan_ids": orph or [],
        })

    documents, problems = [], []
    n_missing = 0
    for d in docs:
        row_ids = {c.id for c in by_doc.get(d.id, [])}
        have = store_ids.get(_collection(d))
        miss = sorted(row_ids - have) if (have is not None and d.status == "ready") else []
        row_issues = []
        if d.status == "ready" and not row_ids:
            row_issues.append("状态为 ready 但没有任何知识块（幻影文档）")
        if d.chunk_count != len(row_ids):
            row_issues.append(f"chunk_count={d.chunk_count} 与实算 {len(row_ids)} 不符")
        if miss:
            row_issues.append(f"{len(miss)} 个知识块无向量（向量召回永久失手，BM25 仍可命中）")
        if row_issues or d.status != "ready":
            documents.append({
                "id": d.id, "title": d.title, "scope": d.scope, "status": d.status,
                "collection": _collection(d), "chunk_count": d.chunk_count,
                "rows": len(row_ids), "indexed": len(row_ids) - len(miss),
                "missing": len(miss), "missing_ids": miss, "issues": row_issues,
            })
        n_missing += len(miss)
        for it in row_issues:
            problems.append(f"doc#{d.id} {d.title}：{it}")

    n_orphan = sum(c["orphan"] or 0 for c in collections)
    for c in collections:
        if c["missing"]:
            problems.append(
                f"集合 {c['name']}：{c['missing']}/{c['expected']} 个知识块缺向量")
        if c["orphan"]:
            problems.append(f"集合 {c['name']}：{c['orphan']} 条向量在 kb_chunks 中无对应行（删除残留）")

    locked = getattr(vs, "unloaded", None) or {}
    for n, reason in sorted(locked.items()):
        problems.append(f"集合 {n} 载入失败已被锁定（{reason}），写入会被拒绝")

    # "无法枚举"不是不一致，而是本次核对没跑完 → 单列 notes，且 ok 不能为真
    notes = []
    if unsupported:
        notes.append(f"以下集合无法枚举 id，未参与核对：{', '.join(unsupported)}")

    return {
        "ok": not (n_missing or n_orphan or problems or unsupported or locked),
        "checked_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "n_documents": len(docs),
            "n_chunks": len(chunk_rows),
            "n_missing": n_missing,
            "n_orphan": n_orphan,
            "n_collections": len(names),
            "unsupported_collections": unsupported,
            "locked_collections": sorted(locked),
        },
        "collections": collections,
        "documents": documents,
        "problems": problems,
        "notes": notes,
    }


def repair_consistency(db: Session, *, vector_store: VectorStore | None = None,
                       embedder=None) -> dict:
    """把「知识块在 DB、向量缺失」的部分重新向量化写回（幂等）。

    只补缺失，**不删 orphan**：删向量是破坏性操作，且 orphan 不影响检索质量（检索按
    kb_chunks 回查，DB 里没有的行本就不会被选中），留待人工确认后再清理。

    返回修复明细与修复后的复检结果；集合被锁定（载入失败）时该集合跳过并给出原因，
    不强行写入（否则会把磁盘上没能载入的旧向量覆盖掉）。
    """
    before = verify_consistency(db, vector_store=vector_store)
    vs = vector_store or get_vector_store()

    # 需要补的 chunk id → 文档（用于补 metadatas 里的 source/page/file_id/scope）
    docs = {d.id: d for d in db.query(KbDocument).all()}
    todo: dict[str, list[KbChunk]] = {}
    for d in before["documents"]:
        if not d["missing_ids"]:
            continue
        rows = (db.query(KbChunk)
                .filter(KbChunk.id.in_(d["missing_ids"]))
                .all())
        todo.setdefault(d["collection"], []).extend(rows)

    repaired = 0
    # 被锁定的集合：verify 因无法枚举而对其"缺失未知"，需在此显式登记为跳过。
    # 否则调用方会看到「修复 0 条 / 跳过 0 个」，把"无法修复"误读成"全库正常"。
    skipped = [
        {"collection": n, "reason": f"集合载入失败已被锁定（{r}），已拒绝写入"}
        for n, r in sorted((getattr(vs, "unloaded", None) or {}).items())
    ]
    emb = None
    for col, rows in sorted(todo.items()):
        if not rows:
            continue
        try:
            if emb is None:
                emb = embedder or get_embedder()
            vs.create_collection(col, dim=emb.dim)
            vs.upsert(
                col,
                ids=[c.id for c in rows],
                vectors=emb.embed_texts([c.text for c in rows]),
                metadatas=[{
                    "chunk_id": c.id, "source": c.source, "page": c.page,
                    "file_id": docs[c.document_id].file_id if c.document_id in docs else None,
                    "scope": docs[c.document_id].scope if c.document_id in docs else None,
                } for c in rows],
            )
            repaired += len(rows)
            logger.info("一致性修复：集合 %s 补写 %d 个知识块向量", col, len(rows))
        except CollectionLockedError as exc:
            skipped.append({"collection": col, "reason": str(exc)})
            logger.error("一致性修复跳过集合 %s：%s", col, exc)

    after = verify_consistency(db, vector_store=vs)
    return {
        "repaired_chunks": repaired,
        "skipped": skipped,
        "before": before["summary"],
        "after": after["summary"],
        "ok": after["ok"],
        "problems": after["problems"],
    }
