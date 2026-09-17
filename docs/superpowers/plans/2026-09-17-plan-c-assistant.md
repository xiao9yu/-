# Plan C：工单 18 智能助教（多模态知识库 + 混合检索重排 RAG 流式问答）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付工单 18 智能助教模块：师生上传文档（PDF/DOCX/PPTX/XLSX/图片）到私有库或公共库 → 多模态解析（文本/表格/图片块）→ bge-m3 向量化入库 → 提问 → 私有库+公共库混合检索（向量+BM25）→ RRF 融合 → bge-reranker 精排 → DeepSeek 流式生成回答，附引用出处与原文（图片/表格直接展示）。

**Architecture:** 复用 Plan A 公共底座（认证/LLM 网关/RAG 引擎/文件服务/解析管线/向量库），新增知识库域：数据模型（kb_documents/kb_chunks）→ 入库服务（解析+分块+向量化+持久化集合 `kb_public`/`kb_user_{id}`）→ 精排服务（bge-reranker，加载失败降级跳过）→ /api/kb 路由（上传/列表/删除/知识块图片/SSE 流式问答）→ Vue3 智能助教页（知识库管理 + 流式对话 + 引用卡片）。Task 1~2 为 Plan A/B 台账遗留加固（含 Plan C 交接清单优先级项）。问答 V1 为单轮（无会话历史），公式块暂不单独识别（图片 OCR 兜底）——两口径在工单18 文档与 README 如实声明。

**Tech Stack:** 底座（FastAPI/SQLAlchemy/OpenAI SDK/rank-bm25/jieba/pymupdf/rapidocr/bge-m3/FAISS 兜底 Milvus）+ sentence-transformers CrossEncoder（bge-reranker-v2-m3）+ 前端 fetch 流式解析 SSE（axios 不支持流式）。

## Global Constraints

- 本计划所有新 Python 文件头部注释用模块专属工单编号：`# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)`；Vue/TS 文件用 `<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18) -->`（HTML）或 `// 工单编号：...`（TS）
- 代码注释用中文；每个任务结束必须 git commit（身份 `huqiaoyu <huqiaoyu@local>`，用 `git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit ...`）
- TDD：后端每个任务先写失败测试→跑测试确认失败→实现→跑测试确认通过→提交；pytest 从 `backend/` 目录运行（`python -m pytest`），默认排除 smoke；改动的既有测试文件按其既有风格追加
- 前端不写单测，以 `npm run build` 通过 + 手动功能清单验证
- 权限模型（设计文档 §5 原文落实）：公共库（`kb_public` 集合）上传/删除仅 `admin`，全员只读检索；私有库（`kb_user_{user_id}` 集合）仅本人上传/删除/检索（**控制器裁定 2026-09-17：admin 可删除他人私有库文档，行使管理权，与本计划图片访问约束"私有库仅 owner/admin"一致；问答检索范围不变**）；`student` 可上传私有库与问答；问答检索范围 = 本人私有库 + 公共库
- 集合命名常量：`kb_public` / `kb_user_{user_id}`（服务层提供 `PUBLIC_COLLECTION` 与 `private_collection(user_id)`）
- 引用标注格式沿用：`[N] 来源：文件名 第X页`（页为空时省略"第X页"）
- 流式问答协议（SSE）：先发 `event: citations`（含 ref_no/source/page/kind/excerpt 全文 text/image_path/chunk_id），再逐段 `event: delta`（`{"text": "..."}`），最后 `event: done`；检索/LLM 失败发 `event: error`（`{"message": "..."}`）——单轮问答，不保存会话历史
- 重排链路：RRF 粗排 → 取前 20 → bge-reranker-v2-m3 精排回 top_k；reranker 加载失败降级跳过精排（log warning，不影响问答）
- 解析为空（含 .doc/.ppt/.xls 二进制老格式）→ 400 友好提示拒绝上传，提示转存 docx/pptx/xlsx；文档保留在白名单以对齐验收格式清单
- 空文本 chunk 不参与向量化（OCR 空图片块同样跳过，防零向量 NaN 污染索引）
- EmbedderError → 路由层 502 友好提示（含 HF_ENDPOINT=https://hf-mirror.com / HF_HUB_OFFLINE=1 指引）
- 上传大小上限：`settings.max_upload_mb = 50`，save_upload 统一执行
- 图片展示：知识块图片走 `GET /kb/chunks/{chunk_id}/image`（公共库 chunk 全员可看，私有库仅 owner/admin；前端 fetch blob 展示，img 标签无法带 Bearer）
- 公式块 V1 口径：解析器不单独产出 formula 块，PDF 公式以文本/图片 OCR 兜底（工单18 文档如实说明）
- V1 范围声明（写进 README）：问答为单轮无历史；多轮会话与"点击展开原文档"富交互后置
- rank-bm25 已钉 >=0.2.2；sentence-transformers 钉 `<6`（兼容 get_sentence_embedding_dimension）

---

### Task 1: 底座加固（台账 Plan A/B 交接清单核心项）

**Files:**
- Modify: `backend/app/services/vector_store.py`（get_vector_store 单例）
- Modify: `backend/app/services/llm_gateway.py`（非可重试错误包 LLMError）
- Modify: `backend/app/services/parser/chunk.py`（split_text 守卫）
- Modify: `backend/app/services/file_service.py`（上传大小上限）
- Modify: `backend/app/services/embeddings.py`（EmbedderError 友好化）
- Modify: `backend/app/services/rag.py`（BM25Index 缓存 + 2 块语料守卫）
- Modify: `backend/app/api/deps.py`（require_roles 工厂）
- Modify: `backend/app/api/files.py`（列表分页参数）
- Modify: `backend/app/config.py`（max_upload_mb）
- Modify: `backend/requirements.txt`（sentence-transformers 钉 <6）
- Test: `backend/tests/test_vector_store.py`、`backend/tests/test_llm_gateway.py`、`backend/tests/test_parser.py`、`backend/tests/test_file_service.py`、`backend/tests/test_embeddings.py`、`backend/tests/test_rag.py`（各追加测试）

**Interfaces:**
- Consumes: 现有各服务文件（Plan A）
- Produces: `get_vector_store()` 模块级单例（可 `reset_vector_store()`）；`require_roles(*roles)` 依赖工厂（Task 6 公共库管理用）；`EmbedderError`（Task 2/4/6 捕获）；`save_upload(..., max_bytes=None)`（Task 4 复用）；`get_bm25_index(chunks)`（Task 4/5 经 hybrid_retrieve 间接受益）；`settings.max_upload_mb`

- [ ] **Step 1: 写失败测试**（各测试文件追加）

`backend/tests/test_vector_store.py` 追加：

```python
def test_get_vector_store_singleton(monkeypatch):
    """get_vector_store 应返回模块级单例（台账 A-1：避免每次重读 FAISS 索引）。"""
    from app.services import vector_store as vs

    calls = []
    class FakeStore:
        def __init__(self): calls.append(1)
    monkeypatch.setattr(vs, "_build_store", lambda: FakeStore())
    vs.reset_vector_store()
    s1 = vs.get_vector_store()
    s2 = vs.get_vector_store()
    assert s1 is s2
    assert len(calls) == 1
    vs.reset_vector_store()
    s3 = vs.get_vector_store()
    assert s3 is not s1          # reset 后重建
    assert len(calls) == 2
    vs.reset_vector_store()
```

`backend/tests/test_llm_gateway.py` 追加：

```python
def test_nonretryable_error_wrapped_as_llmerror(monkeypatch):
    """非可重试 SDK 错误（错 key 401 等）应包成 LLMError 且不重试（台账 A-2）。"""
    from app.services.llm_gateway import LLMError, LLMGateway

    calls = []
    def boom(**kwargs):
        calls.append(1)
        raise RuntimeError("401 Unauthorized")
    gw = LLMGateway(api_key="sk-test")
    monkeypatch.setattr(gw.client.chat.completions, "create", boom)
    import pytest
    with pytest.raises(LLMError, match="大模型调用失败"):
        gw.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1
```

`backend/tests/test_parser.py` 追加：

```python
def test_split_text_rejects_overlap_not_less_than_size():
    import pytest
    from app.services.parser.chunk import split_text
    with pytest.raises(ValueError):
        split_text("abc" * 100, chunk_size=100, overlap=100)

def test_split_text_blank_returns_empty():
    from app.services.parser.chunk import split_text
    assert split_text("   \n  ") == []
```

`backend/tests/test_file_service.py` 追加：

```python
def test_save_upload_exceeds_limit_rejected(tmp_path, db):
    """超过大小上限拒绝上传且不留残留（台账 A-6）。"""
    import io
    import pytest
    from fastapi import UploadFile
    from app.core.exceptions import BizError
    from app.models.file import FileRecord
    from app.services.file_service import save_upload

    file = UploadFile(filename="big.pdf", file=io.BytesIO(b"x" * 100))
    with pytest.raises(BizError, match="大小限制"):
        save_upload(file, owner_id=1, upload_dir=tmp_path, db=db, max_bytes=10)
    assert db.query(FileRecord).count() == 0
    assert list(tmp_path.iterdir()) == []
```

（若 test_file_service.py 的 `db` 夹具名不同，按该文件既有夹具名调整。）

`backend/tests/test_embeddings.py` 追加：

```python
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
```

`backend/tests/test_rag.py` 追加：

```python
def test_bm25_two_chunk_corpus_has_nonzero_scores():
    """2 块语料 BM25 评分应非 0（台账 A-5：旧 rank-bm25 公式 N=df 时 IDF 恒 0）。"""
    from app.services.parser.chunk import Chunk
    from app.services.rag import BM25Index
    chunks = [Chunk(text="梯度下降是机器学习核心优化算法", kind="text", source="a.md"),
              Chunk(text="线性回归用于回归任务", kind="text", source="b.md")]
    hits = BM25Index(chunks).search("梯度下降")
    assert hits and hits[0].score > 0

def test_get_bm25_index_cached():
    from app.services.parser.chunk import Chunk
    from app.services.rag import get_bm25_index
    chunks = [Chunk(text="缓存测试语料一", kind="text", source="a.md"),
              Chunk(text="缓存测试语料二", kind="text", source="b.md")]
    assert get_bm25_index(chunks) is get_bm25_index(chunks)
```

`backend/tests/test_file_service.py` 追加分页测试（该文件已有 client 夹具与 _reg/_token 本地 helper 模式）：

```python
def test_list_files_pagination(client, tmp_path, monkeypatch):
    """GET /api/files 支持 page/size 分页（台账 A-6）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    def _reg(u):
        return client.post("/api/auth/register",
                           json={"username": u, "password": "pass123456", "role": "student"})

    def _token(u):
        return client.post("/api/auth/login",
                           json={"username": u, "password": "pass123456"}).json()["access_token"]

    _reg("p1")
    t = _token("p1")
    headers = {"Authorization": f"Bearer {t}"}
    for i in range(3):
        assert client.post("/api/files/upload",
                           files={"file": (f"f{i}.txt", b"hello", "text/plain")},
                           headers=headers).status_code == 200
    r1 = client.get("/api/files", params={"page": 1, "size": 2}, headers=headers)
    assert r1.status_code == 200 and len(r1.json()) == 2
    r2 = client.get("/api/files", params={"page": 2, "size": 2}, headers=headers)
    assert r2.status_code == 200 and len(r2.json()) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_vector_store.py tests/test_llm_gateway.py tests/test_parser.py tests/test_file_service.py tests/test_embeddings.py tests/test_rag.py -v`
Expected: 新测试 FAIL（AttributeError/ImportError/断言失败）

- [ ] **Step 3: 实现**

`backend/app/services/vector_store.py` 末尾工厂改单例：

```python
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
```

（删除原 `get_vector_store` 实现与 `_factory_lock = None` 残留行。）

`backend/app/services/llm_gateway.py` `_create` 的重试循环整体替换为（新增非可重试错误分支，其余不动）：

```python
        last_exc = None
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(**kwargs)
            except RETRYABLE as exc:
                last_exc = exc
                retry_after = getattr(exc, "response", None)
                retry_after = retry_after.headers.get("retry-after") if retry_after is not None else None
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = self.backoff_base * (2 ** attempt)
                time.sleep(min(delay, 8.0))
            except Exception as exc:
                # 非可重试错误（错 key 401、参数 400 等）直接包成 LLMError，不再空转重试（台账 A-2）
                raise LLMError(f"大模型调用失败：{exc}") from exc
        raise LLMError(f"大模型调用失败（已重试3次）：{last_exc}")
```

`chat_stream` 改为包错误（无重试，同样统一 LLMError）：

```python
    def chat_stream(self, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        """流式输出，逐段 yield 文本。"""
        self._check_key()
        try:
            stream = self.client.chat.completions.create(
                model=settings.deepseek_model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"大模型调用失败：{exc}") from exc
```

`backend/app/services/parser/chunk.py` `split_text` 开头加守卫：

```python
def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """按字符数切块（带重叠），保证向量化粒度与上下文连贯。"""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须为正数：{chunk_size}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap 必须小于 chunk_size，否则切片永不前进：{overlap} >= {chunk_size}")
    if not text.strip():
        return []
```

`backend/app/services/file_service.py`：顶部 import 加 `from ..config import settings`；`save_upload` 签名与写盘改：

```python
def save_upload(file: UploadFile, owner_id: int, upload_dir: Path | str, db: Session,
                max_bytes: int | None = None) -> FileRecord:
    """保存上传文件到 upload_dir（磁盘名用 uuid），并在数据库登记；超过大小上限拒绝。"""
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = _check_ext(file.filename or "unknown")
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = upload_dir / stored_name
    data = file.file.read()
    limit = max_bytes if max_bytes is not None else settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise BizError(400, f"文件超过大小限制（{settings.max_upload_mb}MB）")
    dest.write_bytes(data)
    record = FileRecord(
        filename=file.filename or stored_name,
        stored_name=stored_name,
        ext=ext, size=len(data), owner_id=owner_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
```

（保持函数其余原样：docstring、返回等；原有 `shutil.copyfileobj` 分块写盘被上述读全量+write_bytes 替代，若 `import shutil` 不再使用则一并删除。）

`backend/app/services/embeddings.py` 加异常类并捕获：

```python
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
```

`backend/app/services/rag.py` 加 BM25 缓存。**控制器裁定（2026-09-17）**：BM25 实现由 `BM25Okapi` 改用 `BM25Plus`——本任务 Step 1 的 2 块语料非 0 评分测试与 Okapi 公式互斥（N=df 时 IDF 恒 0），Plus 公式 IDF=ln((N+1)/df) 规避；`import` 区相应改为 `from rank_bm25 import BM25Plus`，实现处加中文注释说明原因。RRF 按排名融合，评分幅度变化不影响融合结果：

```python
_bm25_cache: dict[tuple[str, ...], BM25Index] = {}


def get_bm25_index(chunks: list[Chunk]) -> BM25Index:
    """按语料指纹缓存 BM25 索引（台账 A-5：每查询重建浪费）；缓存上限 8 个，超限整体清空。"""
    key = tuple(c.id for c in chunks)
    if key not in _bm25_cache:
        if len(_bm25_cache) >= 8:
            _bm25_cache.clear()
        _bm25_cache[key] = BM25Index(chunks)
    return _bm25_cache[key]
```

`hybrid_retrieve` 内 `bhits = BM25Index(col.chunks).search(question, top_k)` 改为 `bhits = get_bm25_index(col.chunks).search(question, top_k)`。

`backend/app/api/deps.py` 加依赖工厂（顶部 import 加 `from ..core.exceptions import BizError`、`from ..models.user import Role`）：

```python
def require_roles(*roles: Role):
    """角色守卫依赖：仅指定角色可访问（台账 A-7，Task 6 公共库管理使用）。"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise BizError(403, "权限不足，仅限：" + "、".join(r.value for r in roles))
        return user
    return checker
```

`backend/app/api/files.py` 列表端点加分页参数：

```python
@router.get("", response_model=list[FileOut])
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db),
               page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=500)):
    q = db.query(FileRecord).filter(FileRecord.owner_id == user.id)
    return q.offset((page - 1) * size).limit(size).all()
```

（import 区加 `from fastapi import Query`，若已有则不动；返回形状保持 list 以兼容既有调用。）

`backend/app/config.py` 存储段加：

```python
    max_upload_mb: int = 50
```

`backend/requirements.txt` 改一行：

```
sentence-transformers>=3.0,<6
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_vector_store.py tests/test_llm_gateway.py tests/test_parser.py tests/test_file_service.py tests/test_embeddings.py tests/test_rag.py -v`
Expected: 全部 PASS（含既有测试）

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest` — Expected: 既有 72 条全过、2 deselected，新增 9 条通过（实现者报告实际数字）
Commit:

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(kb): 底座加固——向量库单例/LLM错误包装/分块守卫/上传上限/EmbedderError/BM25缓存/角色依赖/文件分页"
```

---

### Task 2: 备课模块遗留修复（台账 Plan B 终审优先级项）

**Files:**
- Modify: `backend/app/api/prep.py`（导出文件名 sanitize、导出临时目录 try/finally、资源列表/删除端点、search 端点 EmbedderError→502）
- Test: `backend/tests/test_prep_api.py`、`backend/tests/test_prep_export.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `EmbedderError`；`prep_resources.list_resources/delete? `（list_resources 已有；删除需新函数）
- Produces: `GET /prep/courses/{id}/resources`、`DELETE /prep/courses/{id}/resources/{file_id}`（Task 7 前端 PrepCourseView 用）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_prep_api.py` 追加（复用该文件既有 `_register_login(client, username, role)`（返回 headers）与 `_create_course(client, headers, name)`（返回 course dict）helper）：

```python
def test_export_filename_sanitized(client):
    """教案标题含路径字符时导出应成功（修复前：标题含 / 会生成子目录路径导致 500）。"""
    headers = _register_login(client, "t_exp1", "teacher")
    course = _create_course(client, headers)
    lesson = client.post(f"/api/prep/courses/{course['id']}/lessons",
                         json={"title": "教案/第1课:导论?*", "lesson_type": "plan",
                               "content_json": {"标题": "教案/第1课:导论?*"}}, headers=headers).json()
    r = client.get(f"/api/prep/lessons/{lesson['id']}/export", params={"format": "docx"}, headers=headers)
    assert r.status_code == 200
    assert "docx" in r.headers.get("content-disposition", "")


def test_export_tempdir_cleaned_on_error(client, tmp_path, monkeypatch):
    """导出中途异常时临时目录也应清理（台账 B 终审 4）。"""
    from app.api import prep as prep_api
    fake_tmp = tmp_path / "prep_export_fake"
    fake_tmp.mkdir()
    monkeypatch.setattr(prep_api.tempfile, "mkdtemp", lambda **k: str(fake_tmp))

    def boom(content, out_path):
        raise RuntimeError("导出失败")
    monkeypatch.setattr(prep_api.prep_export, "export_lesson_docx", boom)
    headers = _register_login(client, "t_exp2", "teacher")
    course = _create_course(client, headers)
    lesson = client.post(f"/api/prep/courses/{course['id']}/lessons",
                         json={"title": "导出异常教案", "lesson_type": "plan",
                               "content_json": {"标题": "导出异常教案"}}, headers=headers).json()
    r = client.get(f"/api/prep/lessons/{lesson['id']}/export", params={"format": "docx"}, headers=headers)
    assert r.status_code == 500
    assert not fake_tmp.exists()


def test_course_resources_list_and_delete(client, tmp_path, monkeypatch):
    """课程资源列表/删除端点：教师可删，学生 403；磁盘文件同步删除（台账 B 终审 2）。"""
    from app.config import settings
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    headers = _register_login(client, "t_res", "teacher")
    student_headers = _register_login(client, "stu_res", "student")
    course = _create_course(client, headers)
    before = set(upload_dir.iterdir()) if upload_dir.exists() else set()
    up = client.post(f"/api/prep/courses/{course['id']}/resources",
                     files={"file": ("讲义.docx", b"hello", "application/octet-stream")},
                     headers=headers)
    assert up.status_code == 200
    assert len(set(upload_dir.iterdir())) == len(before) + 1
    r = client.get(f"/api/prep/courses/{course['id']}/resources", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1
    fid = r.json()[0]["id"]
    assert client.delete(f"/api/prep/courses/{course['id']}/resources/{fid}",
                         headers=student_headers).status_code == 403
    assert client.delete(f"/api/prep/courses/{course['id']}/resources/{fid}",
                         headers=headers).status_code == 200
    assert client.get(f"/api/prep/courses/{course['id']}/resources", headers=headers).json() == []
    assert set(upload_dir.iterdir()) == before      # 磁盘文件已同步删除


def test_search_embedder_error_502(client, tmp_path, monkeypatch):
    """bge-m3 加载失败时检索返回 502 友好提示（台账 B 终审 3）。"""
    from app.config import settings
    from app.services.embeddings import EmbedderError
    import app.services.prep_resources as pr
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    headers = _register_login(client, "t_emb", "teacher")
    course = _create_course(client, headers)
    # 先传一个真实资源（无资源时检索早退，走不到 embedder）
    client.post(f"/api/prep/courses/{course['id']}/resources",
                files={"file": ("讲义.docx", b"hello", "application/octet-stream")}, headers=headers)
    monkeypatch.setattr(pr, "get_embedder", lambda: (_ for _ in ()).throw(
        EmbedderError("嵌入模型加载失败：offline。HF_ENDPOINT=https://hf-mirror.com")))
    r = client.get(f"/api/prep/courses/{course['id']}/search", params={"q": "梯度下降"}, headers=headers)
    assert r.status_code == 502
    assert "HF_ENDPOINT" in r.json()["detail"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_api.py -v`
Expected: 新测试 FAIL（404/500/无该端点等）

- [ ] **Step 3: 实现** `backend/app/api/prep.py`

import 区加：`import re`、`from ..services.embeddings import EmbedderError`、`from ..services import prep_resources`（已有）、`from ..models.file import FileRecord`。

导出端点 `export_lesson`（既有校验与构建调用保持不变）改为：

```python
    # 格式校验通过后才建临时目录；响应完成后由 BackgroundTask 清理（评审修复：防临时目录泄漏）
    # 标题含路径字符会生成子目录路径/非法文件名，导出前清洗（台账 B 终审 1）
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", lesson.title).strip("_") or "lesson"
    tmp = Path(tempfile.mkdtemp(prefix="prep_export_"))
    out_path = tmp / f"{safe_title}.{format}"
    try:
        if format == "docx":
            if lesson.lesson_type == "case":
                out = prep_export.export_case_docx(content, out_path)
            else:
                out = prep_export.export_lesson_docx(content, out_path)
        elif format == "pptx":
            out = prep_export.export_courseware_pptx(content, out_path)
        else:
            exercises = content.get("习题", []) if lesson.lesson_type == "exercises" \
                else [q for s in content.get("大题", []) for q in s.get("题目", [])]
            out = prep_export.export_exercises_pdf(exercises, lesson.title, out_path)
        return FileResponse(str(out), filename=out.name,
                            media_type="application/octet-stream",
                            background=BackgroundTask(shutil.rmtree, tmp))
    except Exception:
        # 生成中途异常也要清理临时目录（台账 B 终审 4；BackgroundTask 只在响应构造成功时挂载）
        shutil.rmtree(tmp, ignore_errors=True)
        raise
```

（import 区加 `import re`。）

新增资源列表/删除端点（课程区末尾）：

```python
# ---------- 课程资源列表/删除（台账 B 终审 2） ----------


@router.get("/courses/{course_id}/resources")
def list_course_resources(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_course(course_id, user, db)
    return [
        {"id": r.id, "filename": r.filename, "size": r.size, "created_at": r.created_at.isoformat()}
        for r in prep_resources.list_resources(course_id, db)
    ]


@router.delete("/courses/{course_id}/resources/{file_id}")
def delete_course_resource(course_id: int, file_id: int, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    course = _get_course(course_id, user, db)
    if user.role != Role.admin and user.id != course.owner_id:
        raise BizError(403, "仅课程所有者或管理员可删除资源")
    link = db.query(CourseFile).filter(CourseFile.course_id == course_id,
                                       CourseFile.file_id == file_id).first()
    if link is None:
        raise BizError(404, "资源不存在")
    record = db.get(FileRecord, file_id)
    db.delete(link)
    db.commit()
    if record is not None:
        delete_file(file_id, settings.upload_dir, db)
    return {"ok": True}
```

（import 区加 `from ..services.file_service import delete_file`。）

search 端点 `search_course_resources` 与生成资源收集 `_collect_resources` 加 EmbedderError 捕获（两处都调 `prep_resources.search_resources`）：

```python
def search_course_resources(course_id: int, q: str = Query(...), top_k: int = 5,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_course(course_id, user, db)
    try:
        hits = prep_resources.search_resources(course_id, q, settings.upload_dir, db, top_k=top_k)
    except EmbedderError as exc:
        raise BizError(502, str(exc)) from exc
    return {"hits": [{"ref": h["ref"], "score": h["score"], "excerpt": h["chunk"].text[:200],
                      "source": h["chunk"].source, "page": h["chunk"].page} for h in hits]}
```

`_collect_resources` 同法包裹（生成接口 query 非空时也会触发检索）：

```python
    try:
        hits = prep_resources.search_resources(course_id, query, settings.upload_dir, db, top_k=3)
    except EmbedderError as exc:
        raise BizError(502, str(exc)) from exc
```

（import 区加 `from ..services.embeddings import EmbedderError`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_api.py tests/test_prep_export.py -v`
Expected: 全部 PASS（既有 + 新增）

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest` — Expected: 全绿（报告实际数字）
Commit:

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(prep): 导出文件名清洗/临时目录异常清理/资源列表与删除端点/检索EmbedderError→502"
```

---

### Task 3: 知识库数据模型（kb_documents / kb_chunks）

**Files:**
- Create: `backend/app/models/kb.py`
- Create: `backend/tests/test_models_kb.py`

**Interfaces:**
- Consumes: `app.db.Base`（Plan A）
- Produces: `KbDocument`（表 `kb_documents`：id/title/file_id/scope/owner_id/status/error/chunk_count/created_at）、`KbChunk`（表 `kb_chunks`：id(32位 hex 字符串主键)/document_id/kind/text/source/page/meta JSON）——Task 4/5/6 全部依赖；`kb_chunks.source` 列存原始文件名（检索回查必需）

- [ ] **Step 1: 写失败测试** `backend/tests/test_models_kb.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库数据模型测试：文档登记与多模态知识块。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.kb import KbChunk, KbDocument


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def test_kb_document_crud_and_defaults(db):
    doc = KbDocument(title="教材.pdf", file_id=1, scope="private", owner_id=3)
    db.add(doc)
    db.commit()
    got = db.get(KbDocument, doc.id)
    assert got.scope == "private"
    assert got.status == "ready"
    assert got.error == ""
    assert got.chunk_count == 0
    assert got.created_at is not None


def test_kb_chunk_kinds_and_meta(db):
    """多模态知识块：kind 区分 text/table/image，meta 存 image_path 等。"""
    c1 = KbChunk(id="a" * 32, document_id=1, kind="text", text="梯度下降",
                 source="教材.pdf", page=3)
    c2 = KbChunk(id="b" * 32, document_id=1, kind="image", text="",
                 source="教材.pdf", page=3, meta={"image_path": "uploads/extracted/x.png", "file_id": 1})
    db.add_all([c1, c2])
    db.commit()
    got = db.get(KbChunk, "a" * 32)
    assert got.text == "梯度下降"
    assert got.source == "教材.pdf"
    assert db.get(KbChunk, "b" * 32).meta["image_path"].endswith("x.png")


def test_kb_document_public_scope(db):
    db.add(KbDocument(title="公共库资料.pdf", file_id=2, scope="public", owner_id=1))
    db.commit()
    assert db.query(KbDocument).filter(KbDocument.scope == "public").count() == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_models_kb.py -v`
Expected: FAIL（ModuleNotFoundError: app.models.kb）

- [ ] **Step 3: 实现** `backend/app/models/kb.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库数据模型：文档登记（kb_documents）与多模态知识块（kb_chunks）。

入库链路：文件底座落盘（files 表）→ 文档登记 → 解析分块 → 向量化入集合
（kb_public / kb_user_{owner_id}）→ 块落表。检索时按文档状态过滤，从块表回查语料。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class KbDocument(Base):
    """知识库文档登记。scope: public(公共库，admin 维护) | private(个人私有库)。"""

    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))              # 原始文件名
    file_id: Mapped[int] = mapped_column(Integer, index=True)    # FileRecord.id（底座文件）
    scope: Mapped[str] = mapped_column(String(10), default="private")
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(10), default="ready")  # ready | failed
    error: Mapped[str] = mapped_column(String(500), default="")       # 向量化失败原因
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class KbChunk(Base):
    """多模态知识块。kind: text(文本) | table(表格 markdown) | image(图片 OCR + 原图路径)。"""

    __tablename__ = "kb_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4().hex，与向量 id 一致
    document_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(255), default="")   # 原始文件名（引用标注）
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)         # image_path / file_id / sheet 名等
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_models_kb.py -v`
Expected: 3 passed

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest`
Commit:

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(kb): 知识库数据模型 kb_documents/kb_chunks"
```

---

### Task 4: 知识库入库服务（上传→解析→分块→向量化→持久化）

**Files:**
- Create: `backend/app/services/kb_service.py`
- Create: `backend/tests/test_kb_service.py`

**Interfaces:**
- Consumes: Task 3 模型；`save_upload/delete_file/get_file_path`（file_service）；`parse_document`（parser）；`get_embedder`（embeddings，Task 1 加 EmbedderError）；`get_vector_store`（Task 1 单例）；`Chunk`（parser.chunk）
- Produces: `PUBLIC_COLLECTION = "kb_public"`、`private_collection(user_id) -> str`、`add_document(file, scope, user, upload_dir, db, *, vector_store=None, embedder=None) -> KbDocument`、`list_documents(user, db) -> list[KbDocument]`、`delete_document(doc_id, user, upload_dir, db, *, vector_store=None) -> None`——Task 6 路由直接调用；向量 metadatas 键固定 `chunk_id/source/page/file_id/scope`

- [ ] **Step 1: 写失败测试** `backend/tests/test_kb_service.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库入库服务测试：上传解析向量化、列表、删除、权限。"""
import io
from pathlib import Path

import pytest
import pymupdf
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.kb import KbChunk, KbDocument
from app.models.user import Role, User
from app.services import kb_service
from app.services.kb_service import PUBLIC_COLLECTION, add_document, delete_document, list_documents, private_collection


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def _teacher():
    u = User(username="t", hashed_password="x", role=Role.teacher)
    u.id = 3
    return u


def _admin():
    u = User(username="a", hashed_password="x", role=Role.admin)
    u.id = 1
    return u


def _student():
    u = User(username="s", hashed_password="x", role=Role.student)
    u.id = 5
    return u


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[float((i + 1) % 8) / 8 for _ in range(self.dim)] for i in range(len(texts))]

    def embed_query(self, text):
        return self.embed_texts([text])[0]


def _sample_pdf(path: Path):
    """两页演示 PDF（中文文本，保证 BM25 中文分词可命中）。"""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "梯度下降是机器学习核心优化算法", fontname="china-s")
    page = doc.new_page()
    page.insert_text((72, 72), "反向传播基于链式法则计算梯度", fontname="china-s")
    doc.save(str(path))
    doc.close()


def _upload_pdf(path: Path):
    return UploadFile(filename="demo.pdf", file=io.BytesIO(path.read_bytes()))


def test_add_document_private_indexes_into_user_collection(tmp_path, db, monkeypatch):
    holder = {}   # 捕获调用期使用的向量库实例（lambda 每次新建则无法断言落盘）
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store",
                        lambda: holder.setdefault("store", _FakeStore(tmp_path)))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    doc = add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)
    assert doc.scope == "private" and doc.status == "ready" and doc.chunk_count > 0
    rows = db.query(KbChunk).filter(KbChunk.document_id == doc.id).all()
    assert rows and all(r.source == "demo.pdf" for r in rows)
    assert private_collection(3) == "kb_user_3"
    # 向量已写入用户私有集合
    assert "kb_user_3" in holder["store"].ids


def test_add_document_public_only_admin(tmp_path, db, monkeypatch):
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    from app.core.exceptions import BizError
    with pytest.raises(BizError, match="仅管理员"):
        add_document(_upload_pdf(pdf), "public", _teacher(), tmp_path, db)
    doc = add_document(_upload_pdf(pdf), "public", _admin(), tmp_path, db)
    assert doc.scope == "public"
    assert PUBLIC_COLLECTION == "kb_public"


def test_add_document_empty_parse_rejected_and_rolled_back(tmp_path, db, monkeypatch):
    """解析为空（.doc/.ppt/.xls 等）拒绝上传且不留文件与记录。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    monkeypatch.setattr(kb_service, "parse_document", lambda p: [])
    file = UploadFile(filename="legacy.doc", file=io.BytesIO(b"x"))
    from app.core.exceptions import BizError
    with pytest.raises(BizError, match="转换"):
        add_document(file, "private", _teacher(), tmp_path, db)
    assert db.query(KbDocument).count() == 0
    from app.models.file import FileRecord
    assert db.query(FileRecord).count() == 0
    assert list(tmp_path.iterdir()) == []


def test_add_document_embedder_failure_marks_failed(tmp_path, db, monkeypatch):
    """向量化失败时文档保留 status=failed 并记录原因，EmbedderError 上抛。"""
    from app.services.embeddings import EmbedderError
    monkeypatch.setattr(kb_service, "get_embedder", lambda: (_ for _ in ()).throw(
        EmbedderError("嵌入模型加载失败：offline。HF_ENDPOINT=https://hf-mirror.com")))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    with pytest.raises(EmbedderError):
        add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)
    doc = db.query(KbDocument).first()
    assert doc is not None and doc.status == "failed" and "HF_ENDPOINT" in doc.error


def test_list_documents_scope_visibility(tmp_path, db, monkeypatch):
    """列表可见性：本人私有 + 全部公共，他人私有不可见。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)   # 教师私有
    add_document(_upload_pdf(pdf), "public", _admin(), tmp_path, db)      # 公共
    add_document(_upload_pdf(pdf), "private", _admin(), tmp_path, db)     # admin 私有
    mine = list_documents(_teacher(), db)
    assert {d.scope + str(d.owner_id) for d in mine} == {"private3", "public1"}
    assert len(list_documents(_student(), db)) == 1  # 学生只见公共库


def test_delete_document_permissions_and_cleanup(tmp_path, db, monkeypatch):
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    doc = add_document(_upload_pdf(pdf), "private", _teacher(), tmp_path, db)
    from app.core.exceptions import BizError
    with pytest.raises(BizError, match="无权"):
        delete_document(doc.id, _student(), tmp_path, db)
    with pytest.raises(BizError):
        delete_document(999, _teacher(), tmp_path, db)
    delete_document(doc.id, _teacher(), tmp_path, db)
    assert db.query(KbDocument).count() == 0
    assert db.query(KbChunk).count() == 0
    from app.models.file import FileRecord
    assert db.query(FileRecord).count() == 0
    assert list(tmp_path.iterdir()) == []


class _FakeStore:
    """极简落盘向量库替身：方法签名对齐 FaissVectorStore。"""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.indexes = {}
        self.ids = {}
        self.metas = {}

    def _load(self):
        pass

    def create_collection(self, name, dim):
        self.indexes.setdefault(name, [])
        self.ids.setdefault(name, [])
        self.metas.setdefault(name, [])

    def upsert(self, name, ids, vectors, metadatas):
        self.create_collection(name, 8)
        self.ids[name].extend(ids)
        self.metas[name].extend(metadatas)

    def search(self, name, query_vector, top_k, filter_dict=None):
        return []

    def delete(self, name, ids):
        for i in ids:
            if i in self.ids.get(name, []):
                pos = self.ids[name].index(i)
                del self.ids[name][pos]
                del self.metas[name][pos]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_kb_service.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.kb_service）

- [ ] **Step 3: 实现** `backend/app/services/kb_service.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库服务：文档上传 → 多模态解析 → 分块 → 向量化入库 → 列表/删除。

集合约定：公共库 kb_public（admin 维护），私有库 kb_user_{user_id}（每用户一个）。
入库持久化：文档块落 kb_chunks 表，向量落向量库集合（Milvus/FAISS，Task 1 单例）。
"""
from fastapi import UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.file import FileRecord
from ..models.kb import KbChunk, KbDocument
from ..models.user import Role, User
from ..services.embeddings import EmbedderError, get_embedder
from ..services.file_service import delete_file, get_file_path, save_upload
from ..services.parser import parse_document
from ..services.vector_store import VectorStore, get_vector_store

PUBLIC_COLLECTION = "kb_public"


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
    其他未预期异常（向量库故障/解析崩溃）同样记 failed 后上抛（复审修复：不产生"ready 但 0 块"幻影文档）。
    """
    if scope not in ("public", "private"):
        raise BizError(400, "scope 仅支持 public（公共库）或 private（私有库）")
    if scope == "public" and user.role != Role.admin:
        raise BizError(403, "仅管理员可向公共库上传文档")
    record = save_upload(file, owner_id=user.id, upload_dir=upload_dir, db=db)
    doc = KbDocument(title=record.filename, file_id=record.id, scope=scope, owner_id=user.id)
    # 先记 failed 再提交：索引成功后 _index_document 才置 ready
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_kb_service.py -v`
Expected: 6 passed

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest`
Commit:

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(kb): 知识库入库服务——上传/解析/向量化/列表/删除/权限与失败状态"
```

---

### Task 5: 精排服务（bge-reranker）+ RRF→精排 检索链路接入

**Files:**
- Create: `backend/app/services/rerank.py`
- Modify: `backend/app/services/rag.py`（hybrid_retrieve 加 rerank 参数）
- Modify: `backend/app/services/rag_ask.py`（rag_ask 加 rerank 透传）
- Create: `backend/tests/test_rerank.py`

**Interfaces:**
- Consumes: `RagHit`（rag.py）
- Produces: `Reranker.rerank(query, hits, top_n=5) -> list[RagHit]`、`get_reranker() -> Reranker | None`（加载失败返回 None，调用方降级）；`hybrid_retrieve(..., rerank=None)`——非空时 RRF 前 20 → 精排回 top_k；`rag_ask(..., rerank=None)`——Task 6 问答链路使用

- [ ] **Step 1: 写失败测试** `backend/tests/test_rerank.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""精排服务测试：rerank 排序、加载失败降级、hybrid_retrieve 接入。"""
import pytest

from app.services.parser.chunk import Chunk
from app.services.rag import KBCollection, RagHit, hybrid_retrieve


def _hits(n=4):
    return [RagHit(chunk=Chunk(text=f"资料{i}", kind="text", source="a.md", id=f"c{i}")) for i in range(n)]


class FakeModel:
    def __init__(self, scores):
        self.scores = scores

    def predict(self, pairs):
        assert all(len(p) == 2 for p in pairs)
        return self.scores[:len(pairs)]


def test_reranker_sorts_by_score_desc():
    from app.services.rerank import Reranker
    r = Reranker.__new__(Reranker)          # 不触发真实模型下载
    r.model = FakeModel([0.1, 0.9, 0.5])
    out = r.rerank("q", _hits(3), top_n=2)
    assert [h.chunk.id for h in out] == ["c1", "c2"]


def test_get_reranker_returns_none_on_load_failure(monkeypatch):
    """模型加载失败降级返回 None（调用方跳过精排，不阻塞问答）。"""
    from app.services import rerank

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no network")
    monkeypatch.setattr(rerank, "Reranker", Boom)
    monkeypatch.setattr(rerank, "_reranker", None)
    assert rerank.get_reranker() is None


def test_hybrid_retrieve_rerank_limits_and_reorders():
    """rerank 非空时：RRF 结果先取前 20 精排，返回 top_k 条且顺序按精排分。"""
    vs, emb = _FakeVS(), _FakeEmb()
    chunks = [Chunk(text=f"语料{i}", kind="text", source="a.md", id=f"d{i}") for i in range(6)]
    col = KBCollection(name="t", chunks=chunks)
    rerank = lambda q, hits, n: list(reversed(hits[:n]))[:n]   # noqa: E731 反转序验证重排生效
    out = hybrid_retrieve("语料", [col], top_k=3, vector_store=vs, embedder=emb, rerank=rerank)
    assert len(out) == 3
    # 无 rerank 时原路径行为不变：BM25 按 top_k 截断（6 块语料全命中，top_k=6 时融合返回全量 6 条）
    # （控制器裁定：简报原断言 top_k=3 时 len==6 与 BM25Index.search 的 top_k 截断行为矛盾）
    out2 = hybrid_retrieve("语料", [col], top_k=6, vector_store=vs, embedder=emb)
    assert len(out2) == 6


class _FakeVS:
    def search(self, name, query_vector, top_k, filter_dict=None):
        return []


class _FakeEmb:
    dim = 8

    def embed_query(self, text):
        return [0.1] * self.dim
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_rerank.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.rerank / TypeError: hybrid_retrieve 无 rerank 参数）

- [ ] **Step 3: 实现**

`backend/app/services/rerank.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""精排服务：bge-reranker 对 RRF 粗排结果重打分（设计文档 §4.2.2 重排序要求）。"""
import logging

from .rag import RagHit

logger = logging.getLogger("rerank")


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, hits: list[RagHit], top_n: int = 5) -> list[RagHit]:
        """逐对打分（query, chunk.text）→ 按分降序取 top_n。"""
        if not hits:
            return []
        scores = self.model.predict([[query, h.chunk.text] for h in hits])
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [hits[i] for i in order[:top_n]]


_reranker = None


def get_reranker() -> Reranker | None:
    """懒加载单例；模型加载失败返回 None（调用方降级跳过精排，问答不阻塞）。"""
    global _reranker
    if _reranker is None:
        try:
            _reranker = Reranker()
        except Exception as exc:
            logger.warning("bge-reranker 加载失败，降级跳过精排：%s", exc)
            _reranker = False
    return _reranker or None
```

`backend/app/services/rag.py` `hybrid_retrieve` 签名与末尾改：

```python
def hybrid_retrieve(
    question: str,
    collections: list[KBCollection],
    top_k: int = 5,
    *,
    vector_store=None,
    embedder=None,
    rerank=None,
) -> list[RagHit]:
    """混合检索：每个集合各做向量检索 + BM25，全部结果 RRF 融合。
    rerank 非空时：RRF 粗排取前 20 → 精排回 top_k（工单18 重排序链路）。"""
    vs = vector_store or get_vector_store()
    emb = embedder or get_embedder()
    qv = emb.embed_query(question)
    ranked: list[list[RagHit]] = []
    for col in collections:
        by_id = {c.id: c for c in col.chunks}
        vhits = []
        for hit in vs.search(col.name, qv, top_k, filter_dict=col.filter_dict):
            chunk = by_id.get(hit.metadata.get("chunk_id"))
            if chunk is not None:
                vhits.append(RagHit(chunk=chunk, score=float(hit.score)))
        bhits = get_bm25_index(col.chunks).search(question, top_k)
        ranked.append(vhits)
        ranked.append(bhits)
    fused = rrf_fuse(ranked)
    if rerank is not None:
        return rerank(question, fused[:20], top_k)
    return fused
```

`backend/app/services/rag_ask.py` `rag_ask` 签名加参数并透传：

```python
def rag_ask(
    question: str,
    collections: list[KBCollection],
    top_k: int = 5,
    *,
    vector_store=None,
    embedder=None,
    llm=None,
    rerank=None,
) -> RagAnswer:
    """完整链路：混合检索（含可选精排）→ 组装提示词 → LLM 生成 → 引用溯源。"""
    hits = hybrid_retrieve(question, collections, top_k,
                           vector_store=vector_store, embedder=embedder, rerank=rerank)
```

（其余不变。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_rerank.py tests/test_rag.py tests/test_rag_ask.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest`
Commit:

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(kb): bge-reranker 精排服务 + RRF→精排检索链路接入（失败降级跳过）"
```

---

### Task 6: /api/kb 路由（文档管理 + 知识块图片 + SSE 流式问答）

**Files:**
- Create: `backend/app/api/kb.py`
- Modify: `backend/app/main.py`（注册 router）
- Create: `backend/tests/test_kb_api.py`

**Interfaces:**
- Consumes: Task 1 `require_roles/get_current_user`；Task 4 `kb_service`（add_document/list_documents/delete_document）；Task 5 `get_reranker`；`settings.upload_dir`
- Produces: `POST /api/kb/documents`（multipart：file + scope form；公共库仅 admin）、`GET /api/kb/documents`、`DELETE /api/kb/documents/{id}`、`GET /api/kb/chunks/{chunk_id}/image`、`POST /api/kb/ask`（SSE：citations→delta*→done，失败 error）——Task 7 前端全部依赖；SSE 生成器由 kb_service 提供（本任务实现并在 service 内复用）

- [ ] **Step 1: 先给 kb_service 加问答生成器与测试**

`backend/tests/test_kb_service.py` 追加：

```python
def test_ask_stream_events_and_citations(tmp_path, db, monkeypatch):
    """SSE 生成器：citations → delta → done；引用含全文与图片路径。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    store = _FakeStore(tmp_path)
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: store)
    pdf = tmp_path / "demo.pdf"
    _sample_pdf(pdf)
    add_document(_upload_pdf(pdf), "public", _admin(), tmp_path, db)

    class FakeGateway:
        def chat_stream(self, messages, temperature=0.7):
            yield "梯度下降"
            yield "是核心算法"

    monkeypatch.setattr(kb_service, "get_gateway", lambda: FakeGateway())
    out = "".join(kb_service.ask_stream("什么是梯度下降", _student(), db))
    assert "event: citations" in out
    assert "demo.pdf" in out                       # 引用来源为原始文件名
    assert '"text": "梯度下降"' in out             # delta 片段
    assert "event: done" in out
    # 无 reranker 时降级路径同样可用（reranker=None 默认）


def test_ask_stream_error_event_on_llm_failure(tmp_path, db, monkeypatch):
    """LLM 未配置/失败 → event: error（SSE 内友好提示，不炸流）。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))
    from app.services.llm_gateway import LLMError

    class BadGateway:
        def chat_stream(self, messages, temperature=0.7):
            raise LLMError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中配置")
            yield  # pragma: no cover（raise 后不可达，保持生成器形态）

    monkeypatch.setattr(kb_service, "get_gateway", lambda: BadGateway())
    out = "".join(kb_service.ask_stream("你好", _student(), db))
    assert "event: error" in out
    assert "DEEPSEEK_API_KEY" in out
```

`backend/app/services/kb_service.py` 追加（import 区加 `import json`、`from ..services.llm_gateway import LLMError, get_gateway`、`from ..services.rag import KBCollection, hybrid_retrieve`、`from ..services.rag_ask import _select_hits, build_answer_prompt`、`from ..services.parser.chunk import Chunk`、`from typing import Iterator`）：

```python
def ask_stream(question: str, user: User, db: Session, *,
               vector_store=None, embedder=None, reranker=None, gateway=None) -> Iterator[str]:
    """流式问答（SSE 生成器）：检索（私有+公共）→ citations 事件 → LLM 逐段 delta → done。

    失败时发 event: error（检索/LLM 错误均不破坏流协议，前端按事件渲染）。
    V1 单轮：不保存会话历史。
    """

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        # 经本模块 get_embedder 解析嵌入模型后显式传入 hybrid_retrieve：
        # 避免 rag 模块内部再走真实 bge-m3（测试 monkeypatch 本模块 get_embedder 即可覆盖全链路）
        emb = embedder or get_embedder()
        hits = hybrid_retrieve(question, _load_collections(user, db), top_k=5,
                               vector_store=vector_store, embedder=emb, rerank=reranker)
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
        yield sse("citations", citations)
        gw = gateway or get_gateway()
        for piece in gw.chat_stream(build_answer_prompt(question, hits)):
            yield sse("delta", {"text": piece})
        yield sse("done", {})
    except EmbedderError as exc:
        yield sse("error", {"message": str(exc)})
    except LLMError as exc:
        yield sse("error", {"message": str(exc)})
    except BizError as exc:
        yield sse("error", {"message": exc.message})


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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_kb_service.py -v`
Expected: 新增 2 条 FAIL（AttributeError: ask_stream 不存在）

- [ ] **Step 3: 实现 kb_service 追加代码并跑通**

Run: `cd backend && python -m pytest tests/test_kb_service.py -v`
Expected: 8 passed

- [ ] **Step 4: 写路由失败测试** `backend/tests/test_kb_api.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库 API 测试：上传/列表/删除/图片/流式问答/权限。"""
import io

import pymupdf
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import app
from app.api import deps
from app.models.user import Role, User
from app.services import kb_service


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


class FakeStore:
    """进程内存向量库替身。"""

    def __init__(self):
        self.data = {}

    def create_collection(self, name, dim):
        self.data.setdefault(name, [])

    def upsert(self, name, ids, vectors, metadatas):
        self.data.setdefault(name, []).extend(metadatas)

    def search(self, name, query_vector, top_k, filter_dict=None):
        return []

    def delete(self, name, ids):
        pass


class FakeGateway:
    def chat_stream(self, messages, temperature=0.7):
        yield "助教回答片段一"
        yield "片段二"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时 DB + 假向量库/嵌入模型 + 三个角色 headers + Session 工厂。"""
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    from app.config import settings
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))  # 上传不落真实 uploads/
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: FakeStore())
    from fastapi.testclient import TestClient
    client = TestClient(app)
    # 建三个用户
    from app.core.security import create_access_token, hash_password
    s = Session()
    headers = {}
    for name, role in [("teacher", Role.teacher), ("student", Role.student), ("admin", Role.admin)]:
        u = User(username=name, hashed_password=hash_password("p"), role=role, real_name=name)
        s.add(u)
        s.commit()
        s.refresh(u)
        headers[name] = {"Authorization": f"Bearer {create_access_token(u.id, u.role.value)}"}
    s.close()
    yield client, headers, tmp_path, Session
    app.dependency_overrides.clear()


def _sample_pdf(path):
    """一页演示 PDF（中文文本，保证 BM25 命中）。"""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "梯度下降是机器学习核心优化算法", fontname="china-s")
    doc.save(str(path))
    doc.close()


def _upload(client, headers, scope="private"):
    import tempfile
    from pathlib import Path
    pdf = Path(tempfile.mkdtemp()) / "demo.pdf"
    _sample_pdf(pdf)
    with open(pdf, "rb") as f:
        return client.post("/api/kb/documents", files={"file": ("demo.pdf", f, "application/pdf")},
                           data={"scope": scope}, headers=headers)


def test_upload_and_list_documents(env):
    client, headers, _, _ = env
    r = _upload(client, headers["teacher"])
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.json()["chunk_count"] > 0
    r = client.get("/api/kb/documents", headers=headers["student"])
    assert r.status_code == 200 and r.json() == []      # 教师私有，学生不可见
    r = client.get("/api/kb/documents", headers=headers["teacher"])
    assert r.status_code == 200 and len(r.json()) == 1


def test_public_upload_admin_only(env):
    client, headers, _, _ = env
    assert _upload(client, headers["teacher"], scope="public").status_code == 403
    r = _upload(client, headers["admin"], scope="public")
    assert r.status_code == 200
    assert client.get("/api/kb/documents", headers=headers["student"]).json()[0]["scope"] == "public"


def test_delete_permissions(env):
    client, headers, _, _ = env
    doc_id = _upload(client, headers["teacher"]).json()["id"]
    assert client.delete(f"/api/kb/documents/{doc_id}", headers=headers["student"]).status_code == 403
    assert client.delete(f"/api/kb/documents/{doc_id}", headers=headers["teacher"]).status_code == 200
    assert client.get("/api/kb/documents", headers=headers["teacher"]).json() == []


def test_chunk_image_endpoint_permissions(env):
    """图片端点：公共库 chunk 全员可看，他人私有 403。"""
    client, headers, tmp_path, Session = env
    doc_id = _upload(client, headers["admin"], scope="public").json()["id"]
    from app.models.kb import KbChunk
    img = tmp_path / "img.png"
    img.write_bytes(b"PNGDATA")
    chunk = KbChunk(id="e" * 32, document_id=doc_id, kind="image", text="公式图",
                    source="demo.pdf", meta={"image_path": str(img)})
    s = Session()
    s.add(chunk)
    s.commit()
    s.close()
    r = client.get(f"/api/kb/chunks/{'e' * 32}/image", headers=headers["student"])
    assert r.status_code == 200 and r.content == b"PNGDATA"
    # 私有库他人 chunk → 403
    doc_id2 = _upload(client, headers["teacher"]).json()["id"]
    chunk2 = KbChunk(id="f" * 32, document_id=doc_id2, kind="image", text="私有图",
                     source="demo.pdf", meta={"image_path": str(img)})
    s = Session()
    s.add(chunk2)
    s.commit()
    s.close()
    assert client.get(f"/api/kb/chunks/{'f' * 32}/image", headers=headers["student"]).status_code == 403


def test_ask_stream_sse(env):
    client, headers, _, _ = env
    _upload(client, headers["admin"], scope="public")
    import app.services.kb_service as ks
    from unittest import mock
    with mock.patch.object(ks, "get_gateway", lambda: FakeGateway()):
        r = client.post("/api/kb/ask", json={"question": "什么是梯度下降"}, headers=headers["student"])
    assert r.status_code == 200
    body = r.text
    assert "event: citations" in body
    assert "demo.pdf" in body
    assert "助教回答片段一" in body
    assert "event: done" in body


def test_ask_empty_question_400(env):
    client, headers, _, _ = env
    r = client.post("/api/kb/ask", json={"question": "   "}, headers=headers["student"])
    assert r.status_code == 400
```

- [ ] **Step 5: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_kb_api.py -v`
Expected: FAIL（404 无路由）

- [ ] **Step 6: 实现** `backend/app/api/kb.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
"""知识库接口：文档上传/列表/删除、知识块图片、SSE 流式问答。"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..core.exceptions import BizError
from ..db import get_db
from ..models.kb import KbChunk, KbDocument
from ..models.user import Role, User
from ..services import kb_service
from ..services.embeddings import EmbedderError
from ..services.rerank import get_reranker
from .deps import get_current_user

router = APIRouter()


class AskIn(BaseModel):
    question: str


@router.post("/documents")
def upload_document(file: UploadFile = File(...), scope: str = Form("private"),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """上传文档入库：公共库仅 admin（kb_service 校验）；bge-m3 不可用转 502 友好提示。"""
    try:
        doc = kb_service.add_document(file, scope, user, settings.upload_dir, db)
    except EmbedderError as exc:
        raise BizError(502, str(exc)) from exc
    return {"id": doc.id, "title": doc.title, "scope": doc.scope,
            "status": doc.status, "chunk_count": doc.chunk_count}


@router.get("/documents")
def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        {"id": d.id, "title": d.title, "scope": d.scope, "owner_id": d.owner_id,
         "status": d.status, "error": d.error, "chunk_count": d.chunk_count,
         "created_at": d.created_at.isoformat()}
        for d in kb_service.list_documents(user, db)
    ]


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb_service.delete_document(doc_id, user, settings.upload_dir, db)
    return {"ok": True}


@router.get("/chunks/{chunk_id}/image")
def chunk_image(chunk_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """知识块原图：公共库 chunk 全员可看，私有库仅 owner/admin（前端 fetch blob 展示）。"""
    chunk = db.get(KbChunk, chunk_id)
    if chunk is None:
        raise BizError(404, "知识块不存在")
    doc = db.get(KbDocument, chunk.document_id)
    if doc is None:
        raise BizError(404, "文档不存在")
    if doc.scope == "private" and doc.owner_id != user.id and user.role != Role.admin:
        raise BizError(403, "无权访问该图片")
    image_path = (chunk.meta or {}).get("image_path")
    if not image_path:
        raise BizError(404, "该知识块无图片")
    path = Path(image_path)
    if not path.exists():
        raise BizError(404, "图片文件缺失")
    return FileResponse(path)


@router.post("/ask")
def ask(data: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """流式问答（SSE）：citations → delta* → done；失败发 error 事件。"""
    if not data.question.strip():
        raise BizError(400, "问题不能为空")
    return StreamingResponse(
        kb_service.ask_stream(data.question, user, db, reranker=get_reranker()),
        media_type="text/event-stream",
    )
```

`backend/app/main.py`：import 行 `from .api import auth, files, prep` 改 `from .api import auth, files, kb, prep`，注册区加 `app.include_router(kb.router, prefix="/api/kb", tags=["kb"])`。

- [ ] **Step 7: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_kb_api.py tests/test_kb_service.py -v`
Expected: 全部 PASS（14 条）

- [ ] **Step 8: 全量回归 + 提交**

Run: `cd backend && python -m pytest`
Commit:

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(kb): /api/kb 路由——文档管理/知识块图片/SSE流式问答（含权限与友好错误）"
```

---

### Task 7: 前端智能助教页面（知识库管理 + 流式对话 + 引用卡片）+ 备课资源列表 UI + 前端遗留修复

**Files:**
- Create: `frontend/src/api/kb.ts`
- Create: `frontend/src/views/assistant/AssistantView.vue`
- Modify: `frontend/src/router/index.ts`（/module/assistant 精确路由）
- Modify: `frontend/src/views/PlaceholderView.vue`（names 去掉 assistant）
- Modify: `frontend/src/api/prep.ts`（listCourseResources/deleteCourseResource）
- Modify: `frontend/src/views/prep/PrepCourseView.vue`（资源列表 + 删除）
- Modify: `frontend/src/api/http.ts`（401 豁免登录页）
- Modify: `frontend/src/views/LoginView.vue`（catch 未处理 rejection）

**Interfaces:**
- Consumes: Task 6 API（/kb/documents、/kb/chunks/{id}/image、/kb/ask SSE）；Task 2 资源端点；auth store（user.role）
- Produces: 智能助教页（所有角色可用；公共库 tab 仅 admin 可见）

- [ ] **Step 1: 写 API 层** `frontend/src/api/kb.ts`

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
import http from './http'
import { useAuthStore } from '@/stores/auth'

export interface KbDocument {
  id: number; title: string; scope: string; owner_id: number; status: string
  error: string; chunk_count: number; created_at: string
}
export interface KbCitation {
  ref_no: number; source: string; page: number | null; kind: string
  excerpt: string; text: string; image_path: string | null; chunk_id: string
}

export const listKbDocuments = () => http.get('/kb/documents') as Promise<KbDocument[]>

export const uploadKbDocument = (file: File, scope: string) => {
  const form = new FormData()
  form.append('file', file)
  form.append('scope', scope)
  return http.post('/kb/documents', form)
}

export const deleteKbDocument = (id: number) => http.delete(`/kb/documents/${id}`)

/** 知识块原图：接口需 Bearer 鉴权，img 标签无法带头，故 fetch 成 blob 再给 objectURL。 */
export const loadChunkImage = (chunkId: string) =>
  http.get(`/kb/chunks/${chunkId}/image`, { responseType: 'blob' }) as Promise<Blob>

/** 流式问答：axios 不支持流式，用 fetch 手动解析 SSE（citations → delta* → done / error）。 */
export async function askStream(
  question: string,
  onCitations: (citations: KbCitation[]) => void,
  onDelta: (text: string) => void,
): Promise<void> {
  const auth = useAuthStore()
  const resp = await fetch('/api/kb/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
    body: JSON.stringify({ question }),
  })
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => null)
    throw new Error(err?.detail || '请求失败')
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = ''
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!event) continue
      if (event === 'citations') onCitations(JSON.parse(data))
      else if (event === 'delta') onDelta(JSON.parse(data).text)
      else if (event === 'error') throw new Error(JSON.parse(data).message || '生成失败')
    }
  }
}
```

- [ ] **Step 2: 写页面** `frontend/src/views/assistant/AssistantView.vue`

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18) -->
<template>
  <el-row :gutter="16" style="height: calc(100vh - 120px)">
    <el-col :span="8">
      <el-card style="height: 100%">
        <template #header>知识库管理</template>
        <el-tabs v-model="scope" @tab-change="loadDocs">
          <el-tab-pane label="我的私有库" name="private" />
          <el-tab-pane v-if="isAdmin" label="公共库（管理员）" name="public" />
        </el-tabs>
        <el-upload :show-file-list="false" :http-request="onUpload">
          <el-button type="primary" :loading="uploading">
            {{ scope === 'public' ? '上传到公共库' : '上传到私有库' }}
          </el-button>
        </el-upload>
        <el-alert type="info" :closable="false" style="margin-top: 8px"
          title="支持 PDF/DOCX/PPTX/XLSX/图片；.doc/.ppt/.xls 请先转换为新版格式" />
        <div v-for="d in docs" :key="d.id" style="margin-top: 10px; font-size: 13px">
          <div style="display: flex; justify-content: space-between; align-items: center">
            <span>
              <b>{{ d.title }}</b>
              <el-tag size="small" :type="d.scope === 'public' ? 'warning' : 'info'" style="margin-left: 4px">
                {{ d.scope === 'public' ? '公共库' : '私有库' }}
              </el-tag>
              <el-tag v-if="d.status === 'ready'" size="small" type="success">{{ d.chunk_count }} 块</el-tag>
              <el-tooltip v-else :content="d.error || '入库失败'">
                <el-tag size="small" type="danger">失败</el-tag>
              </el-tooltip>
            </span>
            <el-button v-if="isAdmin || d.owner_id === auth.user?.id" size="small" type="text" @click="onDelete(d)">删除</el-button>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :span="16">
      <el-card style="height: 100%">
        <template #header>智能助教问答（引用溯源）</template>
        <div ref="chatBox" style="height: calc(100% - 130px); overflow-y: auto; padding: 8px">
          <div v-for="(m, i) in messages" :key="i" :style="{ textAlign: m.role === 'user' ? 'right' : 'left' }">
            <div :style="bubbleStyle(m.role)">{{ m.text || '思考中……' }}</div>
            <div v-if="m.citations?.length" style="text-align: left">
              <el-card v-for="c in m.citations" :key="c.ref_no" shadow="never" style="margin-top: 8px">
                <template #header>
                  <b>[{{ c.ref_no }}] 来源：{{ c.source }}{{ c.page ? ` 第${c.page}页` : '' }}</b>
                  <el-tag size="small" style="margin-left: 6px">{{ c.kind }}</el-tag>
                </template>
                <el-image v-if="c.kind === 'image'" :src="images[c.chunk_id] || ''" fit="contain"
                  style="max-height: 160px; margin-bottom: 6px" :preview-src-list="[images[c.chunk_id] || '']" />
                <el-skeleton v-if="c.kind === 'image' && !images[c.chunk_id]" :rows="1" animated />
                <pre v-if="c.kind === 'table'" style="white-space: pre-wrap; font-size: 12px; color: #666">{{ c.text }}</pre>
                <el-collapse>
                  <el-collapse-item title="原文摘录">{{ c.text }}</el-collapse-item>
                </el-collapse>
              </el-card>
            </div>
          </div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 10px">
          <el-input v-model="question" placeholder="基于知识库提问，如：梯度下降的学习率怎么选？"
            @keyup.enter="onAsk" :disabled="answering" />
          <el-button type="primary" :loading="answering" @click="onAsk">发送</el-button>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  askStream, deleteKbDocument, listKbDocuments, loadChunkImage,
  uploadKbDocument, type KbCitation, type KbDocument,
} from '@/api/kb'

interface Msg { role: 'user' | 'assistant'; text: string; citations?: KbCitation[] }

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const scope = ref('private')
const docs = ref<KbDocument[]>([])
const uploading = ref(false)
const question = ref('')
const messages = ref<Msg[]>([])
const answering = ref(false)
const chatBox = ref<HTMLElement>()
const images = ref<Record<string, string>>({})   // chunk_id → objectURL（接口需 Bearer，img 标签无法带头，故 fetch blob）

function bubbleStyle(role: string) {
  return {
    display: 'inline-block', maxWidth: '80%', padding: '8px 12px', borderRadius: '8px',
    background: role === 'user' ? '#ecf5ff' : '#f5f7fa', marginTop: '8px', whiteSpace: 'pre-wrap',
    textAlign: 'left', fontSize: '14px',
  }
}

async function loadDocs() {
  // 列表含本人私有库与全部公共库（公共库只读展示，非 admin 无删除按钮）
  docs.value = await listKbDocuments()
}

async function onUpload(opt: any) {
  uploading.value = true
  try {
    await uploadKbDocument(opt.file, scope.value)
    ElMessage.success('已入库')
    await loadDocs()
  } finally { uploading.value = false }
}

async function onDelete(d: KbDocument) {
  await deleteKbDocument(d.id)
  ElMessage.success('已删除')
  await loadDocs()
}

async function loadImg(chunkId: string) {
  if (images.value[chunkId]) return
  const blob = await loadChunkImage(chunkId)
  images.value[chunkId] = URL.createObjectURL(blob)
}

async function onAsk() {
  const q = question.value.trim()
  if (!q || answering.value) return
  question.value = ''
  messages.value.push({ role: 'user', text: q })
  const msg: Msg = { role: 'assistant', text: '' }
  messages.value.push(msg)
  answering.value = true
  try {
    await askStream(q,
      (citations) => {
        msg.citations = citations
        citations.filter((c) => c.kind === 'image').forEach((c) => { void loadImg(c.chunk_id) })
        scrollBottom()
      },
      (text) => { msg.text += text; scrollBottom() })
    if (!msg.text) msg.text = '（无内容）'
  } catch (err: any) {
    msg.text = `生成失败：${err?.message || '未知错误'}`
    ElMessage.error(err?.message || '问答失败')
  } finally { answering.value = false }
}

async function scrollBottom() {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

onMounted(loadDocs)
</script>
```

- [ ] **Step 3: 路由与占位页** `frontend/src/router/index.ts`

在 `/prep/lesson/:id` 行后、`/module/:name` 动态行前插入：

```ts
    { path: '/module/assistant', component: () => import('@/views/assistant/AssistantView.vue') },
```

`frontend/src/views/PlaceholderView.vue` names 对象去掉 `assistant` 项（保留 learn）：

```ts
const names: Record<string, string> = {
  prep: '智能备课（工单17）',
  learn: '个性化学习（工单19）'
}
```

- [ ] **Step 4: 备课资源列表 UI**

`frontend/src/api/prep.ts` 追加：

```ts
export interface CourseResource { id: number; filename: string; size: number; created_at: string }
export const listCourseResources = (courseId: number) =>
  http.get(`/prep/courses/${courseId}/resources`) as Promise<CourseResource[]>
export const deleteCourseResource = (courseId: number, fileId: number) =>
  http.delete(`/prep/courses/${courseId}/resources/${fileId}`)
```

`frontend/src/views/prep/PrepCourseView.vue`：脚本 import 加 `deleteCourseResource, listCourseResources, type CourseResource`；加 `const resources = ref<CourseResource[]>([])`；`load()` 内加 `resources.value = (await listCourseResources(courseId)) as CourseResource[]`；`onUpload` 成功后加 `await load()`；模板"校本资源"卡片内检索结果 div 前加：

```vue
          <div style="margin-top: 12px; font-size: 13px">
            <div v-for="r in resources" :key="r.id" style="display: flex; justify-content: space-between; margin-top: 6px">
              <span>📄 {{ r.filename }}</span>
              <el-button size="small" type="text" @click="onDeleteResource(r)">删除</el-button>
            </div>
          </div>
```

脚本加：

```ts
async function onDeleteResource(r: CourseResource) {
  await deleteCourseResource(courseId, r.id)
  ElMessage.success('资源已删除')
  await load()
}
```

- [ ] **Step 5: 前端遗留修复（台账 A-9）**

`frontend/src/api/http.ts` 响应拦截器 401 行改：

```ts
    if (err.response?.status === 401 && !String(err.config?.url || '').includes('/auth/login')) {
      window.location.href = '/login'
    }
```

`frontend/src/views/LoginView.vue`：登录函数现有 try/finally 补 catch 分支（按该文件现有函数名/结构）：

```ts
    } catch {
      // 错误提示由 http 拦截器统一弹出，这里只兜住未处理 rejection（台账 A-9）
    } finally { loading.value = false }
```

- [ ] **Step 6: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建通过（chunk >500kB 警告与既有同类）

- [ ] **Step 7: 手动功能清单（实现者 curl/浏览器自测后填报告）**

登录 teacher → 智能助教菜单 → 上传私有库 PDF → 列表可见 → 提问（bge-m3 就绪后）流式回答 + 引用卡片 → 删除文档；admin 登录见公共库 tab 上传/删除；student 登录无公共库 tab、可见公共库文档、提问正常、删除他人文档被拒。备课课程页资源列表显示与删除正常。

- [ ] **Step 8: 提交**

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(kb): 前端智能助教页——知识库管理/SSE流式对话/引用卡片 + 备课资源列表UI + 401豁免与登录catch"
```

---

### Task 8: 工单18 测试用例文档 + 公共库演示数据 + README

**Files:**
- Create: `docs/工单18-智能助教-测试用例与结果.md`
- Modify: `backend/scripts/seed_demo_data.py`（加 seed_kb_demo）
- Modify: `README.md`（智能助教模块说明）

**Interfaces:**
- Consumes: `kb_service.add_document`（seed 直接调服务层）；reportlab（复用 make_demo_files 的中文字体注册方式）
- Produces: 工单18 测试用例文档（真实测试名与结果）；seed 幂等预置公共库演示文档

- [ ] **Step 1: 跑全量测试并记录真实数字**

Run: `cd backend && python -m pytest --collect-only -q | tail -5` 与 `cd backend && python -m pytest`
Expected: 全绿。记录总数（如 92 passed, 2 deselected）与本模块测试名清单（test_models_kb/test_kb_service/test_kb_api/test_rerank 全部用例名）。

- [ ] **Step 2: 写文档** `docs/工单18-智能助教-测试用例与结果.md`

结构（仿 docs/工单17-智能备课-测试用例与结果.md）：

```markdown
# 工单 18 智能助教：测试用例与结果

| 项目 | 内容 |
|---|---|
| 关联工单 | 人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18) |
| 模块范围 | 知识库数据模型、入库服务、精排服务、/api/kb 路由、SSE 流式问答、底座加固回归 |
| 测试框架 | pytest（从 backend/ 目录运行，排除 smoke 标记） |
| 测试环境 | Windows 11 / Python 3.x / SQLite（临时目录隔离）/ FAISS 兜底向量库 / bge-m3 本地缓存 / DeepSeek API |
| 执行结果 | 共 N 条：全部通过，2 deselected（smoke） |

## 一、用例清单

| 编号 | 测试名 | 验证点 | 结果 |
|---|---|---|---|
| P1 | test_models_kb.py::test_kb_document_crud_and_defaults | 文档登记与默认值 | 通过 |
| P2 | test_models_kb.py::test_kb_chunk_kinds_and_meta | 多模态块类型与 meta | 通过 |
| ...（全部用例逐行列出，编号连续，测试名与 pytest --collect-only 输出一致） |

## 二、口径说明

- .doc/.ppt/.xls 二进制老格式：上传被 400 拒绝并提示转存 docx/pptx/xlsx（V1 解析器不支持二进制老格式；docx/pptx/xlsx/pdf/图片全覆盖）
- 公式块：解析器不单独产出 formula 块，PDF 公式以文本/图片 OCR 兜底（设计文档 2.2.3 的 V1 简化口径）
- 重排模型 bge-reranker-v2-m3 加载失败时降级跳过精排（仅 RRF 融合），问答不阻塞
- 问答 V1 单轮，不保存会话历史
- 流式问答经 SSE 协议（citations/delta/done/error 事件）
```

（用例表须逐行覆盖 test_models_kb.py、test_kb_service.py、test_kb_api.py、test_rerank.py 以及 Task 1/2 新增用例——编号按文件顺序连续。）

- [ ] **Step 3: seed 加公共库演示数据** `backend/scripts/seed_demo_data.py`

在 `seed_prep_demo(db)` 之后（main 函数调用顺序末位）加：

```python
def seed_kb_demo(db, upload_dir="./uploads"):
    """公共库演示文档：生成 PDF（文本+表格）→ 解析 → 向量化入公共库。幂等：已有 ready 公共文档则跳过。"""
    from app.models.kb import KbDocument
    exists = db.query(KbDocument).filter(KbDocument.scope == "public",
                                         KbDocument.status == "ready").first()
    if exists:
        print("公共库已有演示文档，跳过")
        return
    from app.models.user import User
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        print("admin 不存在，跳过公共库演示数据")
        return
    pdf_path = Path(tempfile.gettempdir()) / "kb_demo_人工智能导论知识库.pdf"
    _build_kb_demo_pdf(pdf_path)
    from app.services import kb_service
    from app.services.embeddings import EmbedderError
    from fastapi import UploadFile
    with open(pdf_path, "rb") as f:
        file = UploadFile(filename="人工智能导论知识库.pdf", file=f)
        try:
            doc = kb_service.add_document(file, "public", admin, upload_dir, db)
            print(f"公共库演示文档已入库：{doc.title}（{doc.chunk_count} 块）")
        except EmbedderError as exc:
            print(f"bge-m3 不可用，跳过公共库演示数据：{exc}")


def _build_kb_demo_pdf(path):
    """3 页演示 PDF：第 1 页文本（梯度下降）、第 2 页表格（优化器对比）、第 3 页文本（反向传播）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    def _register_font():
        # 与 make_demo_files 相同策略：Windows 用 simhei.ttf，否则 STSong-Light
        try:
            pdfmetrics.registerFont(TTFont("demo", r"C:\Windows\Fonts\simhei.ttf"))
        except Exception:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            return "STSong-Light"
        return "demo"

    font = _register_font()
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4

    def draw_text_page(lines):
        y = h - 80
        c.setFont(font, 14)
        for line in lines:
            c.drawString(60, y, line)
            y -= 30

    draw_text_page([
        "人工智能导论知识库",
        "一、梯度下降：机器学习最常用的优化算法。",
        "核心思想：沿损失函数梯度反方向迭代更新参数，使损失逐步减小。",
        "学习率控制每步更新幅度：过大会震荡发散，过小则收敛缓慢。",
    ])
    c.showPage()
    c.setFont(font, 14)
    c.drawString(60, h - 80, "二、常见优化器对比")
    rows = [["优化器", "特点"], ["SGD", "每次用单样本梯度，收敛慢"], ["Adam", "自适应学习率，收敛快且稳定"]]
    x0, y0, cell_w, cell_h = 60, h - 140, 240, 30
    c.setFont(font, 12)
    for r, row in enumerate(rows):
        for col, cell in enumerate(row):
            c.rect(x0 + col * cell_w, y0 - r * cell_h, cell_w, cell_h)
            c.drawString(x0 + col * cell_w + 8, y0 - r * cell_h + 10, cell)
    c.showPage()
    draw_text_page([
        "三、反向传播：利用链式法则逐层计算梯度，",
        "是训练深度神经网络的基础算法，与梯度下降配合完成参数更新。",
    ])
    c.save()
```

（import 区加 `import tempfile`、`from pathlib import Path`，若已有则不动。）

main 函数调用链末加：

```python
    seed_kb_demo(db)
```

- [ ] **Step 4: 验证 seed**

Run: `cd backend && python scripts/seed_demo_data.py`
Expected: 打印"公共库演示文档已入库：人工智能导论知识库.pdf（N 块）"；再跑一次打印"公共库已有演示文档，跳过"（幂等）。

- [ ] **Step 5: 更新 README**（"智能备课"模块说明之后加）

```markdown
### 智能助教（工单 18）

- **多模态知识库**：上传 PDF/DOCX/PPTX/XLSX/图片 → 解析为文本/表格/图片块（OCR+原图保留）→ bge-m3 向量化入库（Milvus，异常自动退回 FAISS）。公共库由 admin 预置维护（seed 脚本已入库演示文档《人工智能导论知识库.pdf》），私有库按用户隔离。
- **混合检索重排**：提问后私有库+公共库各取向量 top-k 与 BM25 top-k → RRF 融合 → bge-reranker-v2-m3 精排（加载失败自动降级跳过精排）。
- **流式问答**：DeepSeek 流式生成（SSE），回答附引用溯源卡片（文件名+页码+原文摘录；图片块直显原图、表格块展示结构化文本）。
- **模型**：bge-m3（向量化）+ bge-reranker-v2-m3（精排），首次运行需联网下载（约 3GB），可设 `HF_ENDPOINT=https://hf-mirror.com` 加速；已有缓存可设 `HF_HUB_OFFLINE=1` 离线加载。
- **V1 范围说明**：问答为单轮（不保存会话历史）；.doc/.ppt/.xls 二进制老格式请先转换为 docx/pptx/xlsx 再上传；公式暂以文本/图片 OCR 兜底识别。
```

- [ ] **Step 6: 提交**

```bash
cd "C:\Users\38668\Desktop\项目\数字人\edu-agent-platform" && git add -A && git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "docs(kb): 工单18测试用例文档 + 公共库演示数据seed + README模块说明"
```

---

## 完成标准（Plan C）

1. 全量 pytest 通过（含 Task 1/2 加固回归；smoke 2 条照旧排除）
2. 知识库全链路：上传（公共/私有）→ 多模态解析 → 向量化入库 → 列表/删除
3. 混合检索 + RRF + bge-reranker 精排（加载失败降级）
4. SSE 流式问答 + 引用溯源（文件名+页码+摘录原文；图片/表格展示）
5. 权限：公共库仅 admin 写；私有库隔离（他人 403）；学生可上传私有库与问答
6. 前端 `npm run build` 通过；智能助教页浏览器人工验证清单（Task 7 Step 7）
7. docs/工单18-智能助教-测试用例与结果.md（真实测试名与结果，口径说明齐全）
8. seed 公共库演示数据幂等；README 模块说明 + V1 范围声明
9. 逐任务 git commit（身份 huqiaoyu <huqiaoyu@local>）
10. 台账 Plan A/B 交接清单核心项落地：向量库单例、LLM 错误包装、split_text 守卫、.doc/.ppt/.xls 友好拒绝、BM25 缓存、上传大小上限+files 分页、require_roles、sentence-transformers 钉 <6、401 登录页豁免、LoginView catch、导出文件名 sanitize、资源列表/删除端点、bge-m3 失败 502 友好化、导出异常清理
