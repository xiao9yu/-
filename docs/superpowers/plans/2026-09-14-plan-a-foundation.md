# Plan A：项目脚手架 + 公共底座 + 工单16 文档（D1-D2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 edu-agent-platform 前后端骨架与公共底座（认证/LLM网关/文件服务/文档解析管线/向量库/混合检索RAG引擎），并产出工单16架构文档。

**Architecture:** 单体平台四层架构（Vue3 前端 → FastAPI 后端 → 智能服务层 → SQLite+Milvus Lite+文件存储）。本计划只做公共底座，四个功能模块（工单17~20）在 Plan B~E 中按工单顺序垂直交付。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy + OpenAI SDK(DeepSeek) + sentence-transformers(bge-m3) + pymilvus(Milvus Lite)/faiss-cpu + rank-bm25 + jieba + PyMuPDF/python-docx/python-pptx/openpyxl + rapidocr-onnxruntime；前端 Vue3 + Vite + Element Plus + Pinia + Vue Router + axios。

**计划序列总览**（本文件是 Plan A，其余阶段开始前再写）：

| 计划 | 内容 | 对应排期 |
|---|---|---|
| Plan A（本文件） | 脚手架+公共底座+工单16文档 | D1-D2 |
| Plan B | 工单17 智能备课 | D3-D4 |
| Plan C | 工单18 智能助教（多模态知识库+RAG问答） | D5-D6 |
| Plan D | 工单19 个性化学习推荐（Neo4j+画像+错题本） | D7-D8 |
| Plan E | 工单20 面试AI复盘（FunASR） | D9-D10 |
| Plan F | 集成联调+全部文档产出+验收彩排 | D11-D14 |

## Global Constraints

- Python 3.12.7（本机 anaconda3），Node v24.17.0，npm 11.13.0（已确认）
- 后端端口 8000，前端端口 5173，Vite 代理 `/api` → `http://localhost:8000`
- **每个新建 Python 文件头部必须有工单编号注释**，格式（工单备注要求）：
  `# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)`；模块专属文件用对应编号（如 `...-智能备课任务(17)`）；Vue 文件用 HTML 注释 `<!-- 工单编号：... -->`
- 代码注释用中文；每个任务结束必须 git commit
- TDD：后端每个任务先写失败测试→跑测试确认失败→实现→跑测试确认通过→提交
- 前端任务不写单测，以 `npm run build` 通过 + 手动功能清单验证
- pytest 从 `backend/` 目录运行；默认排除 smoke 标记（需下载大模型），smoke 用 `pytest -m smoke -o addopts=""` 运行
- `backend/.env` 不入库（gitignore），仅提交 `.env.example`
- bge-m3 模型约 2GB、torch 约 2GB，下载慢时设 `HF_ENDPOINT=https://hf-mirror.com`（镜像）
- bge-reranker 精排延后到 Plan C（工单18 阶段启用），Plan A 的 RAG 用 RRF 融合完成重排序
- 用户角色枚举：`student`（学生）/ `teacher`（教师）/ `counselor`（就业指导）/ `admin`（管理员）

---

### Task 1: 后端骨架 + 配置 + 数据库 + 全局异常处理

**Files:**
- Create: `backend/requirements.txt`、`backend/pytest.ini`、`backend/app/__init__.py`、`backend/app/config.py`、`backend/app/db.py`、`backend/app/main.py`、`backend/app/core/__init__.py`、`backend/app/core/exceptions.py`
- Create: `backend/tests/__init__.py`、`backend/tests/conftest.py`、`backend/tests/test_health.py`
- Create: 根目录 `.gitignore`

**Interfaces:**
- Produces: `app.config.settings`（Settings 实例）、`app.db.Base / engine / SessionLocal / get_db`、`app.core.exceptions.BizError / register_exception_handlers`、`app.main.app`（FastAPI 实例，含 `/api/health`）

- [ ] **Step 1: 写失败测试** `backend/tests/test_health.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

同时创建 `backend/tests/conftest.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

- [ ] **Step 2: 创建依赖清单与骨架文件**

`backend/requirements.txt`：

```
fastapi>=0.115
uvicorn[standard]>=0.30
sqlalchemy>=2.0
pydantic-settings>=2.3
pyjwt>=2.8
bcrypt>=4.1
openai>=1.40
python-multipart>=0.0.9
pymupdf>=1.24
python-docx>=1.1
python-pptx>=1.0
openpyxl>=3.1
rapidocr-onnxruntime>=1.3
pymilvus>=2.4.6
faiss-cpu>=1.8
rank-bm25>=0.2.2
jieba>=0.42
sentence-transformers>=3.0
pytest>=8.0
```

`backend/app/config.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""全局配置：从 backend/.env 读取，未配置项使用默认值。"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "edu-agent-platform"
    secret_key: str = "edu-agent-dev-secret-key-9f8e7d6c5b4a3210-change-me"
    access_token_expire_minutes: int = 60 * 24
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 存储
    db_url: str = "sqlite:///./data/app.db"
    upload_dir: str = "./uploads"
    # 向量与模型
    embedding_model: str = "BAAI/bge-m3"
    vector_backend: str = "milvus"  # milvus | faiss
    milvus_uri: str = "./data/milvus.db"

    class Config:
        env_file = ".env"


settings = Settings()
```

`backend/app/db.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""数据库引擎与会话。SQLite 开发期，SQLAlchemy 模型即数据库设计产出物。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_is_sqlite = settings.db_url.startswith("sqlite")
engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`backend/app/core/exceptions.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""业务异常与全局异常处理器：所有接口返回结构化错误 JSON，前端不白屏。"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BizError(Exception):
    """业务异常：携带 HTTP 状态码与用户可读的中文提示。"""

    def __init__(self, status_code: int = 400, message: str = "操作失败"):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
```

`backend/app/main.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.exceptions import register_exception_handlers
from .db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # 启动时建表（实训简化，不引入 Alembic）
    yield


app = FastAPI(title="edu-agent-platform", lifespan=lifespan)
register_exception_handlers(app)


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

`backend/pytest.ini`：

```ini
[pytest]
pythonpath = .
markers =
    smoke: 需要下载大模型/启动外部依赖的冒烟测试，默认不跑，用 -m smoke 执行
addopts = -m "not smoke"
```

根目录 `.gitignore`（项目根）：

```
backend/.env
backend/uploads/
backend/data/
__pycache__/
*.pyc
node_modules/
frontend/dist/
.DS_Store
.superpowers/
```

- [ ] **Step 3: 安装依赖**

Run: `cd backend && pip install -r requirements.txt`
Expected: 全部安装成功（torch 约 2GB，耗时较长；慢则用 `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 后端骨架+配置+数据库+全局异常处理（工单16-20公共底座）"
```

---

### Task 2: 用户模型 + 注册/登录/JWT 认证

**Files:**
- Create: `backend/app/models/__init__.py`、`backend/app/models/user.py`、`backend/app/core/security.py`、`backend/app/api/__init__.py`、`backend/app/api/deps.py`、`backend/app/api/auth.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/app/main.py`（挂载 auth 路由）

**Interfaces:**
- Consumes: `app.db.Base`、`app.config.settings`
- Produces: `app.models.user.User / Role`；`app.core.security.hash_password / verify_password / create_access_token / decode_token`；`app.api.deps.get_current_user`（依赖，返回 User，无 token 抛 401）；路由 `POST /api/auth/register`、`POST /api/auth/login`、`GET /api/auth/me`

- [ ] **Step 1: 写失败测试** `backend/tests/test_auth.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
def _register(client, username="stu1", role="student"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": "pass123456", "role": role, "real_name": "张三"},
    )


def test_register_login_me_flow(client):
    assert _register(client).status_code == 200
    resp = client.post("/api/auth/login", json={"username": "stu1", "password": "pass123456"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "student"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "stu1"


def test_register_duplicate_username_400(client):
    _register(client)
    resp = _register(client)
    assert resp.status_code == 400
    assert "已存在" in resp.json()["detail"]


def test_login_wrong_password_401(client):
    _register(client)
    resp = client.post("/api/auth/login", json={"username": "stu1", "password": "wrong"})
    assert resp.status_code == 401


def test_me_without_token_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_register_invalid_role_422(client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "x", "password": "pass123456", "role": "boss", "real_name": ""},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_auth.py -v`
Expected: FAIL（ModuleNotFoundError: app.models.user）

- [ ] **Step 3: 实现模型与安全工具**

`backend/app/models/user.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""用户模型：四种角色覆盖工单17(教师)/18(师生)/19(学生)/20(就业指导+教师)。"""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Role(str, enum.Enum):
    student = "student"      # 学生
    teacher = "teacher"      # 教师
    counselor = "counselor"  # 就业指导
    admin = "admin"          # 管理员


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
    real_name: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

`backend/app/core/security.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""密码哈希与 JWT 签发/校验。"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from ..config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
```

`backend/app/api/deps.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""通用依赖：当前登录用户解析。"""
import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.security import decode_token
from ..db import get_db
from ..models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(cred.credentials)
        user_id = int(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError, TypeError):
        # 坏签名/过期/缺失或非数字 sub 统一按 401 处理，避免 500
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

`backend/app/api/auth.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""认证接口：注册/登录/当前用户。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..core.security import create_access_token, hash_password, verify_password
from ..db import get_db
from ..models.user import Role, User
from .deps import get_current_user

router = APIRouter()


class RegisterIn(BaseModel):
    username: str
    password: str
    role: Role = Role.student
    real_name: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    real_name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/register", response_model=UserOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise BizError(400, "用户名已存在")
    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=data.role,
        real_name=data.real_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if user is None or not verify_password(data.password, user.hashed_password):
        raise BizError(401, "用户名或密码错误")
    return TokenOut(access_token=create_access_token(user.id, user.role.value), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
```

`backend/app/models/__init__.py` 与 `backend/app/api/__init__.py` 为空文件。修改 `backend/app/main.py`，在 `register_exception_handlers(app)` 后加：

```python
from .api import auth  # 放在文件顶部 import 区

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_auth.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 用户模型与JWT认证（工单16-20公共底座）"
```

---

### Task 3: LLM 网关（DeepSeek 统一封装）

**Files:**
- Create: `backend/app/services/__init__.py`、`backend/app/services/llm_gateway.py`
- Create: `backend/tests/test_llm_gateway.py`

**Interfaces:**
- Consumes: `app.config.settings`
- Produces: `LLMError`；`LLMGateway(api_key=None, base_url=None, backoff_base=0.5, http_client=None)`；方法 `chat(messages) -> str`、`chat_json(messages, temperature=0.3) -> dict`、`chat_stream(messages, temperature=0.7) -> Iterator[str]`；`get_gateway() -> LLMGateway`（懒加载单例）。Plan B~E 全部通过它调 DeepSeek。

- [ ] **Step 1: 写失败测试** `backend/tests/test_llm_gateway.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import json

import httpx
import pytest

from app.services.llm_gateway import LLMError, LLMGateway

CHAT_JSON = {
    "id": "1", "object": "chat.completion", "created": 1, "model": "deepseek-chat",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "你好"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _gw(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMGateway(api_key="sk-test", base_url="https://api.test", backoff_base=0.01, http_client=client)


def test_chat_returns_content():
    def handler(request):
        return httpx.Response(200, json=CHAT_JSON)

    assert _gw(handler).chat([{"role": "user", "content": "hi"}]) == "你好"


def test_chat_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": {"message": "busy"}}, headers={"retry-after": "0"})
        return httpx.Response(200, json=CHAT_JSON)

    assert _gw(handler).chat([{"role": "user", "content": "hi"}]) == "你好"
    assert calls["n"] == 3


def test_chat_raises_after_max_retries():
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "busy"}}, headers={"retry-after": "0"})

    with pytest.raises(LLMError):
        _gw(handler).chat([{"role": "user", "content": "hi"}])


def test_chat_json_repairs_bad_json():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        body = json.loads(request.content)
        if calls["n"] == 1:
            resp = dict(CHAT_JSON, choices=[{"index": 0, "message": {"role": "assistant", "content": "not-json"}, "finish_reason": "stop"}])
        else:
            resp = dict(CHAT_JSON, choices=[{"index": 0, "message": {"role": "assistant", "content": '{"ok": true}'}, "finish_reason": "stop"}])
        return httpx.Response(200, json=resp)

    assert _gw(handler).chat_json([{"role": "user", "content": "输出 JSON"}]) == {"ok": True}
    assert calls["n"] == 2


def test_chat_json_requires_json_keyword_in_prompt():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        resp = dict(CHAT_JSON, choices=[{"index": 0, "message": {"role": "assistant", "content": '{"a": 1}'}, "finish_reason": "stop"}])
        return httpx.Response(200, json=resp)

    _gw(handler).chat_json([{"role": "user", "content": "给我结果"}])
    assert "JSON" in seen["body"]["messages"][-1]["content"]


def test_chat_stream_yields_deltas():
    from unittest.mock import patch

    gw = LLMGateway(api_key="sk-test", base_url="https://api.test", backoff_base=0.01)

    class Delta:
        def __init__(self, content): self.content = content

    class Choice:
        def __init__(self, content): self.delta = Delta(content)

    class Chunk:
        def __init__(self, content): self.choices = [Choice(content)]

    class FakeStream:
        def __iter__(self):
            return iter([Chunk("你"), Chunk("好")])

    with patch.object(gw.client.chat.completions, "create", return_value=FakeStream()):
        assert list(gw.chat_stream([{"role": "user", "content": "hi"}])) == ["你", "好"]


def test_chat_without_api_key_raises():
    gw = LLMGateway(api_key="", base_url="https://api.test")
    with pytest.raises(LLMError, match="DEEPSEEK_API_KEY"):
        gw.chat([{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_llm_gateway.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.llm_gateway）

- [ ] **Step 3: 实现 LLM 网关** `backend/app/services/llm_gateway.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""LLM 网关：统一封装 DeepSeek 调用。
功能：超时/限流指数退避重试、JSON 结构化输出与修复重试、流式输出、用量日志。
各功能模块只调网关，不直接碰 OpenAI SDK。
"""
import json
import logging
import re
import time
from typing import Iterator

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from ..config import settings

logger = logging.getLogger("llm")

RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


class LLMError(Exception):
    """LLM 调用失败（重试耗尽/未配置密钥等）。"""


class LLMGateway:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        backoff_base: float = 0.5,
        http_client: httpx.Client | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.deepseek_api_key
        self.backoff_base = backoff_base
        kwargs = {}
        if http_client is not None:
            kwargs["http_client"] = http_client
        self.client = OpenAI(
            api_key=self.api_key or "sk-empty",
            base_url=base_url or settings.deepseek_base_url,
            timeout=60.0,
            max_retries=0,  # 重试由网关自管
            **kwargs,
        )

    def _check_key(self):
        if not self.api_key:
            raise LLMError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中配置")

    def _create(self, messages, temperature, response_format=None, stream=False):
        self._check_key()
        kwargs = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if response_format:
            kwargs["response_format"] = response_format
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
        raise LLMError(f"大模型调用失败（已重试3次）：{last_exc}")

    @staticmethod
    def _log_usage(resp):
        usage = getattr(resp, "usage", None)
        if usage is not None:
            logger.info("LLM用量 prompt=%s completion=%s", usage.prompt_tokens, usage.completion_tokens)

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """普通对话，返回文本。"""
        resp = self._create(messages, temperature)
        self._log_usage(resp)
        return resp.choices[0].message.content or ""

    def chat_json(self, messages: list[dict], temperature: float = 0.3) -> dict:
        """结构化输出：要求模型返回 JSON，解析失败自动修复重试一次。"""
        msgs = [dict(m) for m in messages]
        if "JSON" not in msgs[-1].get("content", ""):
            msgs[-1]["content"] += "\n请以 JSON 格式输出，不要输出其他内容。"
        for attempt in range(2):
            resp = self._create(
                msgs, temperature, response_format={"type": "json_object"}
            )
            self._log_usage(resp)
            content = resp.choices[0].message.content or ""
            parsed = self._parse_json(content)
            if parsed is not None:
                return parsed
            # 修复重试：把错误反馈给模型
            msgs.append({"role": "assistant", "content": content})
            msgs.append({"role": "user", "content": "上次输出不是合法 JSON，请重新只输出合法 JSON。"})
        raise LLMError("大模型 JSON 输出解析失败")

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        # 去掉 markdown 代码围栏再试
        m = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def chat_stream(self, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        """流式输出，逐段 yield 文本。"""
        self._check_key()
        stream = self.client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    """懒加载单例。"""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_llm_gateway.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: LLM网关（DeepSeek统一封装，重试/JSON修复/流式/用量日志）"
```

---

### Task 4: 文件服务（上传/下载/列表）

**Files:**
- Create: `backend/app/models/file.py`、`backend/app/services/file_service.py`、`backend/app/api/files.py`
- Create: `backend/tests/test_file_service.py`
- Modify: `backend/app/main.py`（挂载 files 路由）

**Interfaces:**
- Consumes: `app.db.Base`、`app.api.deps.get_current_user`
- Produces: `FileRecord`（模型）；`app.services.file_service.save_upload(file, owner_id, upload_dir, db) -> FileRecord`、`get_file_path(record, upload_dir) -> Path`、`delete_file(record_id, upload_dir, db)`（db 会话由调用方传入）；路由 `POST /api/files/upload`（multipart `file`）、`GET /api/files/{id}/download`、`GET /api/files`。Plan B（多媒体插入）与 Plan C（文档上传）复用它。

- [ ] **Step 1: 写失败测试** `backend/tests/test_file_service.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import io

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import BizError
from app.db import Base
from app.services.file_service import delete_file, get_file_path, save_upload


@pytest.fixture
def db(tmp_path):
    """服务函数直测：独立临时库，不污染开发库。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def _upload(tmp_path, db, filename="教案.md", content=b"hello"):
    return save_upload(
        UploadFile(filename=filename, file=io.BytesIO(content)),
        owner_id=1, upload_dir=tmp_path, db=db,
    )


def test_save_upload_creates_record_and_file(tmp_path, db):
    record = _upload(tmp_path, db)
    assert record.filename == "教案.md"
    path = get_file_path(record, tmp_path)
    assert path.exists() and path.read_bytes() == b"hello"


def test_save_upload_rejects_bad_ext(tmp_path, db):
    with pytest.raises(BizError, match="不支持"):
        _upload(tmp_path, db, filename="virus.exe")


def test_save_upload_allows_image_and_audio(tmp_path, db):
    for name in ["a.png", "b.jpg", "c.wav", "d.mp3", "e.pdf", "f.pptx", "g.xlsx"]:
        assert _upload(tmp_path, db, filename=name).id > 0


def test_delete_file_removes_disk(tmp_path, db):
    record = _upload(tmp_path, db)
    path = get_file_path(record, tmp_path)
    delete_file(record.id, upload_dir=tmp_path, db=db)
    assert not path.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_file_service.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.file_service）

- [ ] **Step 3: 实现文件服务**

`backend/app/models/file.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文件记录：所有上传的文档/图片/音频统一登记。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))     # 原始文件名
    stored_name: Mapped[str] = mapped_column(String(100))  # 磁盘名（uuid.后缀）
    ext: Mapped[str] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

`backend/app/services/file_service.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文件服务：上传落盘+登记、路径解析、删除。
db 会话由调用方传入（API 层用请求级会话，测试用临时库）。
"""
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.file import FileRecord

ALLOWED_EXTS = {
    # 文档（工单18 验收格式清单）
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    # 文本与笔记
    "md", "txt",
    # 图片
    "png", "jpg", "jpeg", "gif", "bmp",
    # 音视频（工单17 多媒体、工单20 面试录音）
    "mp3", "wav", "m4a", "aac", "mp4", "webm",
}


def _check_ext(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTS:
        raise BizError(400, f"不支持的文件类型：{ext or '无后缀'}")
    return ext


def save_upload(file: UploadFile, owner_id: int, upload_dir: Path | str, db: Session) -> FileRecord:
    """保存上传文件到 upload_dir（磁盘名用 uuid），并在数据库登记。"""
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = _check_ext(file.filename or "unknown")
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = upload_dir / stored_name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    record = FileRecord(
        filename=file.filename or stored_name,
        stored_name=stored_name,
        ext=ext,
        size=dest.stat().st_size,
        owner_id=owner_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_file_path(record: FileRecord, upload_dir: Path | str) -> Path:
    return Path(upload_dir) / record.stored_name


def delete_file(record_id: int, upload_dir: Path | str, db: Session) -> None:
    """删除磁盘文件与数据库记录（不存在则忽略磁盘错误）。"""
    record = db.get(FileRecord, record_id)
    if record is None:
        return
    path = Path(upload_dir) / record.stored_name
    if path.exists():
        path.unlink()
    db.delete(record)
    db.commit()
```

`backend/app/api/files.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文件接口：上传/下载/我的文件列表。"""
from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..core.exceptions import BizError
from ..db import get_db
from ..models.file import FileRecord
from ..models.user import User
from ..services.file_service import delete_file, get_file_path, save_upload
from .deps import get_current_user

router = APIRouter()


class FileOut(BaseModel):
    id: int
    filename: str
    ext: str
    size: int
    created_at: object

    class Config:
        from_attributes = True


@router.post("/upload", response_model=FileOut)
def upload(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_upload(file, owner_id=user.id, upload_dir=settings.upload_dir, db=db)


@router.get("", response_model=list[FileOut])
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(FileRecord).filter(FileRecord.owner_id == user.id).order_by(FileRecord.id.desc()).all()


@router.get("/{file_id}/download")
def download(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.get(FileRecord, file_id)
    if record is None or record.owner_id != user.id:
        raise BizError(404, "文件不存在")
    path = get_file_path(record, settings.upload_dir)
    if not path.exists():
        raise BizError(404, "文件已丢失")
    return FileResponse(path, filename=record.filename)


@router.delete("/{file_id}")
def remove(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.get(FileRecord, file_id)
    if record is None or record.owner_id != user.id:
        raise BizError(404, "文件不存在")
    delete_file(file_id, settings.upload_dir, db)
    return {"ok": True}
```

修改 `backend/app/main.py` 挂载路由：

```python
from .api import auth, files  # 顶部 import

app.include_router(files.router, prefix="/api/files", tags=["files"])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_file_service.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 文件服务（上传/下载/列表，类型白名单）"
```

---

### Task 5: 文档解析管线（多模态：文本/表格/图片/公式）

**Files:**
- Create: `backend/app/services/parser/__init__.py`、`backend/app/services/parser/chunk.py`、`backend/app/services/parser/pdf_parser.py`、`backend/app/services/parser/office_parser.py`、`backend/app/services/parser/image_parser.py`
- Create: `backend/tests/test_parser.py`
- Modify: `backend/app/models/file.py` 不涉及；本任务无 DB 依赖

**Interfaces:**
- Consumes: 无（纯解析，依赖 pymupdf/python-docx/python-pptx/openpyxl/rapidocr）
- Produces: `app.services.parser.chunk.Chunk`（字段：`text: str, kind: str, source: str, id: str, page: int|None, meta: dict`，kind 取值 `text|table|image|formula`）；`split_text(text, chunk_size=800, overlap=100) -> list[str]`；`parse_document(path: Path) -> list[Chunk]`（按扩展名分发）；`ocr_image(image_path) -> str`。Plan C（工单18）入库与 Plan B（工单17 资源检索）复用它。

- [ ] **Step 1: 写失败测试** `backend/tests/test_parser.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import io
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw
from pptx import Presentation
from pymupdf import open as open_pdf

from app.services.parser import parse_document
from app.services.parser.chunk import split_text


@pytest.fixture
def docx_with_table_image(tmp_path) -> Path:
    """生成包含段落、表格、图片的 docx 样例。"""
    doc = Document()
    doc.add_paragraph("机器学习是人工智能的一个分支。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "模型"; table.cell(0, 1).text = "准确率"
    table.cell(1, 0).text = "决策树"; table.cell(1, 1).text = "0.85"
    # 生成一张图片插入
    img = Image.new("RGB", (80, 40), "white")
    ImageDraw.Draw(img).text((5, 10), "ML")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    doc.add_picture(buf)
    path = tmp_path / "讲义.docx"
    doc.save(path)
    return path


@pytest.fixture
def pptx_sample(tmp_path) -> Path:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "人工智能导论"
    path = tmp_path / "课件.pptx"
    prs.save(path)
    return path


@pytest.fixture
def xlsx_sample(tmp_path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(["知识点", "掌握人数"])
    ws.append(["梯度下降", 30])
    path = tmp_path / "成绩.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def pdf_sample(tmp_path) -> Path:
    path = tmp_path / "教材.pdf"
    doc = open_pdf()
    page = doc.new_page()
    page.insert_text((72, 72), "神经网络由多层神经元组成。")
    doc.save(path); doc.close()
    return path


def test_split_text_with_overlap():
    parts = split_text("A" * 30, chunk_size=10, overlap=2)
    assert len(parts) == 4  # 10+10+10+6（最后一片不足一个整块）
    assert parts[0] == "A" * 10


def test_parse_docx_kinds(docx_with_table_image):
    chunks = parse_document(docx_with_table_image)
    kinds = {c.kind for c in chunks}
    assert "text" in kinds and "table" in kinds and "image" in kinds
    table_chunk = next(c for c in chunks if c.kind == "table")
    assert "模型" in table_chunk.text and "决策树" in table_chunk.text


def test_parse_pptx_text(pptx_sample):
    chunks = parse_document(pptx_sample)
    assert any("人工智能导论" in c.text for c in chunks)


def test_parse_xlsx_table(xlsx_sample):
    chunks = parse_document(xlsx_sample)
    assert any(c.kind == "table" and "梯度下降" in c.text for c in chunks)


def test_parse_pdf_text(pdf_sample):
    chunks = parse_document(pdf_sample)
    assert any("神经网络" in c.text for c in chunks)
    assert all(c.page == 1 for c in chunks)


def test_parse_image_ocr(monkeypatch, tmp_path):
    from app.services.parser import image_parser

    img = Image.new("RGB", (80, 40), "white")
    path = tmp_path / "photo.png"
    img.save(path)
    monkeypatch.setattr(image_parser, "ocr_image", lambda p: "识别出的板书文字")
    chunks = parse_document(path)
    assert len(chunks) == 1
    assert chunks[0].kind == "image"
    assert chunks[0].text == "识别出的板书文字"
    assert chunks[0].meta["image_path"] == str(path)


def test_parse_unsupported_returns_empty(tmp_path):
    path = tmp_path / "x.xyz"
    path.write_text("abc")
    assert parse_document(path) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_parser.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.parser）

- [ ] **Step 3: 实现解析管线**

`backend/app/services/parser/chunk.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""统一的内容块结构：工单18 多模态解析的基础数据结构。"""
import uuid
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """解析产物块。kind: text(文本) | table(表格) | image(图片) | formula(公式)。"""
    text: str
    kind: str
    source: str              # 来源文件名
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    page: int | None = None  # PDF 页码（从 1 开始），Office 文档为 None
    meta: dict = field(default_factory=dict)  # 附加信息：image_path、sheet 名等


def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """按字符数切块（带重叠），保证向量化粒度与上下文连贯。"""
    if len(text) <= chunk_size:
        return [text]
    parts = []
    start = 0
    while start < len(text):
        parts.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return [p for p in parts if p.strip()]
```

`backend/app/services/parser/image_parser.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""图片解析：OCR 提取文字（rapidocr = PaddleOCR 模型的 ONNX 实现，安装轻量）。"""
from pathlib import Path

from .chunk import Chunk

_ocr_engine = None


def _get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_image(image_path) -> str:
    """OCR 识别图片中的文字，多行用换行连接。"""
    result, _ = _get_engine()(str(image_path))
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def parse_image(path: Path) -> list[Chunk]:
    text = ocr_image(path)
    return [Chunk(
        text=text,
        kind="image",
        source=path.name,
        meta={"image_path": str(path)},
    )]
```

`backend/app/services/parser/pdf_parser.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""PDF 解析：按页抽取文本与内嵌图片（图片 OCR + 保留原图）。"""
import uuid
from pathlib import Path

import pymupdf

from .chunk import Chunk, split_text
from .image_parser import ocr_image


def parse_pdf(path: Path, extract_dir: Path | None = None) -> list[Chunk]:
    doc = pymupdf.open(str(path))
    chunks: list[Chunk] = []
    for idx, page in enumerate(doc, start=1):
        # 1) 文本
        text = page.get_text().strip()
        for part in split_text(text):
            chunks.append(Chunk(text=part, kind="text", source=path.name, page=idx))
        # 2) 内嵌图片 → 存盘 + OCR（提取目录默认 uploads/extracted）
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = doc.extract_image(xref)
            except Exception:
                continue
            img_path = (extract_dir or Path("uploads/extracted")) / f"{uuid.uuid4().hex}.{pix['ext']}"
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(pix["image"])
            ocr_text = ocr_image(img_path)
            chunks.append(Chunk(
                text=ocr_text,
                kind="image",
                source=path.name,
                page=idx,
                meta={"image_path": str(img_path)},
            ))
    doc.close()
    return chunks
```

`backend/app/services/parser/office_parser.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""Office 解析：docx（段落/表格/图片保序）、pptx（幻灯片文本）、xlsx（表格化）。"""
import uuid
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from openpyxl import load_workbook
from pptx import Presentation

from .chunk import Chunk, split_text
from .image_parser import ocr_image


def _flush(buf: list[str], source: str, chunks: list[Chunk]):
    text = "\n".join(buf).strip()
    if text:
        for part in split_text(text):
            chunks.append(Chunk(text=part, kind="text", source=source))
    buf.clear()


def _table_to_markdown(table) -> str:
    rows = []
    for row in table.rows:
        cells = [c.text.replace("\n", " ").strip() for c in row.cells]
        rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return ""
    ncols = rows[0].count("|") - 1
    header_sep = "| " + " | ".join(["---"] * ncols) + " |"
    return "\n".join([rows[0], header_sep, *rows[1:]])


def parse_docx(path: Path, extract_dir: Path | None = None) -> list[Chunk]:
    doc = Document(str(path))
    chunks: list[Chunk] = []
    buf: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            para = [t.text for t in child.iter(qn("w:t")) if t.text]
            has_pic = len(child.findall(".//" + qn("pic:pic"))) > 0
            if has_pic:
                _flush(buf, path.name, chunks)
                # 提取内嵌图片
                img_rid = None
                for blip in child.iter(qn("a:blip")):
                    img_rid = blip.get(qn("r:embed"))
                    break
                if img_rid and img_rid in doc.part.related_parts:
                    blob = doc.part.related_parts[img_rid].blob
                    img_path = (extract_dir or Path("uploads/extracted")) / f"{uuid.uuid4().hex}.png"
                    img_path.parent.mkdir(parents=True, exist_ok=True)
                    img_path.write_bytes(blob)
                    chunks.append(Chunk(
                        text=ocr_image(img_path),
                        kind="image",
                        source=path.name,
                        meta={"image_path": str(img_path)},
                    ))
            else:
                buf.append("".join(para))
        elif tag == qn("w:tbl"):
            _flush(buf, path.name, chunks)
            table = None
            # 用 python-docx 的 Table 包装当前 w:tbl 元素
            from docx.table import Table
            table = Table(child, doc)
            md = _table_to_markdown(table)
            if md:
                chunks.append(Chunk(text=md, kind="table", source=path.name))
    _flush(buf, path.name, chunks)
    return chunks


def parse_pptx(path: Path) -> list[Chunk]:
    prs = Presentation(str(path))
    chunks: list[Chunk] = []
    for idx, slide in enumerate(prs.slides, start=1):
        lines = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        lines.append(t)
        if lines:
            for part in split_text("\n".join(lines)):
                chunks.append(Chunk(text=part, kind="text", source=path.name, page=idx))
    return chunks


def parse_xlsx(path: Path, max_rows: int = 200) -> list[Chunk]:
    wb = load_workbook(str(path), read_only=True, data_only=True)
    chunks: list[Chunk] = []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_rows:
                rows.append(["（表格过长，已截断）"])
                break
            if any(v is not None for v in row):
                cells = ["" if v is None else str(v).replace("\n", " ") for v in row]
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            header_sep = "| " + " | ".join(["---"] * (rows[0].count("|") - 1)) + " |"
            chunks.append(Chunk(
                text="\n".join([rows[0], header_sep, *rows[1:]]),
                kind="table",
                source=path.name,
                meta={"sheet": ws.title},
            ))
    wb.close()
    return chunks
```

`backend/app/services/parser/__init__.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文档解析管线入口：PDF/DOCX/PPTX/XLSX/图片 → 多模态 Chunk 列表。"""
from pathlib import Path

from .chunk import Chunk, split_text  # noqa: F401
from .image_parser import ocr_image, parse_image  # noqa: F401
from .office_parser import parse_docx, parse_pptx, parse_xlsx  # noqa: F401
from .pdf_parser import parse_pdf  # noqa: F401

_PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".doc": None,  # 老格式：提示用户转存 docx（V1 不支持二进制 doc）
    ".pptx": parse_pptx,
    ".xlsx": parse_xlsx,
    ".png": parse_image, ".jpg": parse_image, ".jpeg": parse_image,
    ".gif": parse_image, ".bmp": parse_image,
}


def parse_document(path: Path | str) -> list[Chunk]:
    """按扩展名分发解析器；不支持的格式返回空列表。"""
    path = Path(path)
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        return []
    return parser(path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_parser.py -v`
Expected: PASS（7 passed）。若 docx 图片提取测试失败，检查 `qn("pic:pic")` 命名空间写法并修复。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 文档解析管线（PDF/DOCX/PPTX/XLSX/图片多模态Chunk）"
```

---

### Task 6: Embedding 服务（bge-m3）

**Files:**
- Create: `backend/app/services/embeddings.py`
- Create: `backend/tests/test_embeddings.py`（smoke）

**Interfaces:**
- Consumes: `app.config.settings`
- Produces: `Embedder.embed_texts(texts) -> list[list[float]]`、`Embedder.embed_query(text) -> list[float]`、`Embedder.dim`；`get_embedder() -> Embedder`（懒加载单例）。Plan B/C 的向量化统一走它。

- [ ] **Step 1: 写冒烟测试** `backend/tests/test_embeddings.py`

```python
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
```

- [ ] **Step 2: 实现 Embedding 服务** `backend/app/services/embeddings.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""Embedding 服务：本地 bge-m3（DeepSeek 无 embedding API，本地免费离线）。"""
import threading

from ..config import settings


class Embedder:
    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or settings.embedding_model
        self.model = SentenceTransformer(self.model_name)
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


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = Embedder()
        return _embedder
```

- [ ] **Step 3: 下载模型并运行冒烟测试**

下载慢时先执行（PowerShell）：`$env:HF_ENDPOINT="https://hf-mirror.com"`（Git Bash：`export HF_ENDPOINT=https://hf-mirror.com`）

Run: `cd backend && pytest tests/test_embeddings.py -v -m smoke -o addopts=""`
Expected: PASS（首次运行自动下载 bge-m3 约 2.2GB，耗时取决于网速）

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: Embedding服务（本地bge-m3，懒加载单例）"
```

---

### Task 7: 向量库（接口 + FAISS 实现 + Milvus Lite 实现）

**Files:**
- Create: `backend/app/services/vector_store.py`
- Create: `backend/tests/test_vector_store.py`

**Interfaces:**
- Consumes: `app.config.settings`
- Produces: `SearchHit(id, score, metadata)`；`VectorStore`（抽象基类：`create_collection(name, dim)`、`upsert(name, ids, vectors, metadatas)`、`search(name, query_vector, top_k, filter_dict=None) -> list[SearchHit]`、`delete(name, ids)`）；`FaissVectorStore(data_dir)`、`MilvusVectorStore(uri)`、`get_vector_store() -> VectorStore`（按 `settings.vector_backend` 选择，Milvus 初始化失败自动退回 FAISS）。Plan C 知识库入库与检索走此接口。

- [ ] **Step 1: 写失败测试** `backend/tests/test_vector_store.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import pytest

from app.services.vector_store import FaissVectorStore, get_vector_store


@pytest.fixture
def store(tmp_path):
    return FaissVectorStore(data_dir=tmp_path / "faiss")


def _seed(store):
    store.create_collection("kb1", dim=3)
    store.upsert(
        "kb1",
        ids=["a", "b"],
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        metadatas=[{"chunk_id": "c-a", "source": "x.pdf"}, {"chunk_id": "c-b", "source": "y.pdf"}],
    )


def test_upsert_and_search(store):
    _seed(store)
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert hits[0].id == "a"
    assert hits[0].metadata["chunk_id"] == "c-a"
    assert hits[0].score >= hits[1].score


def test_search_with_filter(store):
    _seed(store)
    hits = store.search("kb1", [0.7, 0.7, 0.0], top_k=2, filter_dict={"source": "y.pdf"})
    assert len(hits) == 1
    assert hits[0].id == "b"


def test_delete_removes(store):
    _seed(store)
    store.delete("kb1", ["a"])
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=2)
    assert all(h.id != "a" for h in hits)


def test_factory_faiss_backend(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "vector_backend", "faiss")
    store = get_vector_store()
    assert isinstance(store, FaissVectorStore)


@pytest.mark.smoke
def test_milvus_lite_smoke(tmp_path):
    """Milvus Lite 冒烟：本机跑不起来时此测试可跳过（FAISS 兜底）。"""
    milvus = pytest.importorskip("pymilvus")
    from app.services.vector_store import MilvusVectorStore
    uri = str(tmp_path / "milvus.db")
    store = MilvusVectorStore(uri=uri)
    store.create_collection("kb1", dim=3)
    store.upsert(
        "kb1", ids=["a"],
        vectors=[[1.0, 0.0, 0.0]],
        metadatas=[{"chunk_id": "c-a", "source": "x.pdf"}],
    )
    hits = store.search("kb1", [1.0, 0.0, 0.0], top_k=1)
    assert hits[0].id == "a"
```

> 注：评审修复回归测试（3 个：FAISS 过滤先排序后过滤返回满 top_k、metadata 返回副本、Milvus 表达式双引号转义）见评审修复记录（`.superpowers/sdd/task-7-report.md` 修复记录小节）。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_vector_store.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.vector_store）

- [ ] **Step 3: 实现向量库** `backend/app/services/vector_store.py`

```python
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


_factory_lock = None


def get_vector_store() -> VectorStore:
    """工厂：按配置选择后端；Milvus 异常时自动退回 FAISS（同为工单17 推荐方案）。"""
    if settings.vector_backend == "faiss":
        return FaissVectorStore()
    try:
        return MilvusVectorStore(settings.milvus_uri)
    except Exception as exc:  # 本机环境跑不起 Milvus 时兜底
        logger.warning("Milvus 初始化失败，自动退回 FAISS：%s", exc)
        return FaissVectorStore()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_vector_store.py -v`
Expected: PASS（7 passed + 1 skipped，含 3 个修复回归测试）。Milvus 冒烟另跑：`pytest tests/test_vector_store.py::test_milvus_lite_smoke -v -m smoke -o addopts=""`，通过则 Milvus Lite 可用；失败且报环境错误时保持 FAISS 默认（在 `.env` 设 `VECTOR_BACKEND=faiss`）。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 向量库抽象（Milvus Lite + FAISS 兜底，工单17推荐方案）"
```

---

### Task 8: BM25 + 混合检索 + RRF 重排序

**Files:**
- Create: `backend/app/services/rag.py`
- Create: `backend/tests/test_rag.py`

**Interfaces:**
- Consumes: `app.services.parser.chunk.Chunk`、`app.services.vector_store.SearchHit/VectorStore`
- Produces: `tokenize(text) -> list[str]`（jieba 分词）；`RagHit(chunk, score)`；`KBCollection(name, chunks, filter_dict)`；`BM25Index(chunks).search(query, top_k) -> list[RagHit]`；`rrf_fuse(ranked_lists, k=60) -> list[RagHit]`；`hybrid_retrieve(question, collections, top_k, *, vector_store=None, embedder=None) -> list[RagHit]`。工单18 的"混合检索+重排序"核心算法即本任务。

- [ ] **Step 1: 写失败测试** `backend/tests/test_rag.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
from app.services.parser.chunk import Chunk
from app.services.rag import BM25Index, KBCollection, hybrid_retrieve, rrf_fuse, tokenize
from app.services.vector_store import FaissVectorStore, SearchHit


def _chunks():
    return [
        Chunk(text="梯度下降是机器学习最基础的优化算法", kind="text", source="教材.pdf", id="c1"),
        Chunk(text="房价预测案例使用线性回归模型", kind="text", source="笔记.md", id="c2"),
        Chunk(text="计算机网络的七层模型", kind="text", source="教材.pdf", id="c3"),
    ]


def test_tokenize_chinese():
    tokens = tokenize("梯度下降优化算法")
    assert "梯度" in tokens or "梯度下降" in tokens
    assert len(tokens) >= 2


def test_bm25_relevant_first():
    idx = BM25Index(_chunks())
    hits = idx.search("梯度下降是什么", top_k=2)
    assert hits[0].chunk.id == "c1"


def test_rrf_fuse_dedup_and_rank():
    chunks = _chunks()
    list1 = [SearchHit(id="c1", score=0.9, metadata={"chunk_id": "c1"})]
    list2 = [SearchHit(id="c2", score=0.8, metadata={"chunk_id": "c2"})]
    # 转成 RagHit 列表：c1 在两个列表都出现
    a = [type("H", (), {"chunk": chunks[0], "score": 0.9})()]
    b = [type("H", (), {"chunk": chunks[0], "score": 0.8})(), type("H", (), {"chunk": chunks[1], "score": 0.7})()]
    fused = rrf_fuse([a, b])
    assert fused[0].chunk.id == "c1"  # 出现两次融合分更高
    assert len(fused) == 2


def test_hybrid_retrieve_merges_vector_and_bm25(tmp_path):
    class FakeEmbedder:
        def embed_query(self, text):
            # 与 c1 向量相近
            return [1.0, 0.0, 0.0]

    store = FaissVectorStore(data_dir=tmp_path / "faiss")
    store.create_collection("kb", dim=3)
    store.upsert(
        "kb",
        ids=["c1", "c2", "c3"],
        vectors=[[1.0, 0, 0], [0.9, 0.1, 0], [0.0, 1.0, 0]],
        metadatas=[{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c3"}],
    )
    col = KBCollection(name="kb", chunks=_chunks())
    hits = hybrid_retrieve("计算机网络", [col], top_k=2, vector_store=store, embedder=FakeEmbedder())
    ids = [h.chunk.id for h in hits]
    assert "c1" in ids  # 向量命中：查询向量 [1,0,0] 的最近邻
    assert "c3" in ids  # 仅 BM25 可命中：c3 向量与查询向量正交，但文本匹配"计算机网络"
```

（评审修复：查询改为"计算机网络"，断言 BM25 独有命中 c3——原 brief 测试在删除 BM25 半程时依然通过，未能验证混合命题）

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_rag.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.rag）

- [ ] **Step 3: 实现 RAG 检索** `backend/app/services/rag.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 检索核心：BM25 关键词 + 向量检索混合，RRF 融合重排序。
工单18「混合检索→重排序→最优结果」的算法实现；工单17 资源检索复用。
"""
from dataclasses import dataclass, field

import jieba
from rank_bm25 import BM25Okapi

from .embeddings import get_embedder
from .parser.chunk import Chunk
from .vector_store import get_vector_store


def tokenize(text: str) -> list[str]:
    """中文分词（搜索引擎模式，利于短查询召回）。"""
    return [t for t in jieba.lcut_for_search(text) if t.strip()]


@dataclass
class RagHit:
    chunk: Chunk
    score: float = 0.0


@dataclass
class KBCollection:
    """一次检索涉及的集合：向量集合名 + 对应语料（供 BM25 与 chunk 回查）。"""
    name: str
    chunks: list[Chunk]
    filter_dict: dict | None = None  # 私有库过滤，如 {"owner_id": "3"}


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c.text) for c in chunks]) if chunks else None

    def search(self, query: str, top_k: int = 10) -> list[RagHit]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [RagHit(chunk=self.chunks[i], score=float(scores[i])) for i in order if scores[i] > 0]


def rrf_fuse(ranked_lists: list[list[RagHit]], k: int = 60) -> list[RagHit]:
    """RRF 融合：同一 chunk 在多个排序列表中得分累加（1/(k+rank+1)），按融合分降序。"""
    fused: dict[str, tuple[RagHit, float]] = {}
    for hits in ranked_lists:
        for rank, h in enumerate(hits):
            s = 1.0 / (k + rank + 1)
            if h.chunk.id in fused:
                fused[h.chunk.id] = (fused[h.chunk.id][0], fused[h.chunk.id][1] + s)
            else:
                fused[h.chunk.id] = (h, s)
    return [h for h, _ in sorted(fused.values(), key=lambda x: -x[1])]


def hybrid_retrieve(
    question: str,
    collections: list[KBCollection],
    top_k: int = 5,
    *,
    vector_store=None,
    embedder=None,
) -> list[RagHit]:
    """混合检索：每个集合各做向量检索 + BM25，全部结果 RRF 融合。"""
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
        bhits = BM25Index(col.chunks).search(question, top_k)
        ranked.append(vhits)
        ranked.append(bhits)
    return rrf_fuse(ranked)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_rag.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: BM25+向量混合检索与RRF重排序（工单18核心算法）"
```

---

### Task 9: RAG 问答组装（rag_ask + 引用溯源）

**Files:**
- Create: `backend/app/services/rag_ask.py`
- Create: `backend/tests/test_rag_ask.py`

**Interfaces:**
- Consumes: `app.services.rag.hybrid_retrieve/RagHit/KBCollection`、`app.services.llm_gateway.LLMGateway`
- Produces: `RagAnswer(answer: str, citations: list[dict])`；`build_answer_prompt(question, hits, max_chars=4000) -> list[dict]`；`rag_ask(question, collections, top_k=5, *, vector_store=None, embedder=None, llm=None) -> RagAnswer`。Plan C 对话接口直接调 `rag_ask`。

- [ ] **Step 1: 写失败测试** `backend/tests/test_rag_ask.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import re

from app.services.parser.chunk import Chunk
from app.services.rag import KBCollection
from app.services.rag_ask import build_answer_prompt, rag_ask


class FakeLLM:
    """记录调用并返回固定答案。"""
    def __init__(self, answer="资料[1]说明了梯度下降的原理。"):
        self.answer = answer
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.answer


def _col():
    return KBCollection(name="kb", chunks=[
        Chunk(text="梯度下降通过沿负梯度方向迭代更新参数。", kind="text", source="教材.pdf", page=3, id="c1"),
        Chunk(text="房价预测案例：线性回归拟合房价。", kind="text", source="笔记.md", page=None, id="c2"),
        # 第三块与查询无关，但必须存在：rank_bm25 的 IDF 在 2 篇语料、df=1 时恒为 0，
        # 加上 BM25Index 只保留 score>0，2 篇语料下 BM25 永远召不回任何块（Task 8 测试同样用 3 篇）。
        Chunk(text="计算机网络的七层模型。", kind="text", source="教材.pdf", page=8, id="c3"),
    ])


class FakeVS:
    def search(self, name, qv, top_k, filter_dict=None):
        return []


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0, 1.0, 0.0]


def test_build_answer_prompt_numbers_context():
    hits = [type("H", (), {"chunk": _col().chunks[0], "score": 0.9})()]
    messages = build_answer_prompt("什么是梯度下降", hits)
    system = messages[0]["content"]
    assert "[1]" in system
    assert "教材.pdf" in system and "第3页" in system
    assert "什么是梯度下降" in messages[1]["content"]


def test_rag_ask_returns_citations():
    llm = FakeLLM()
    result = rag_ask(
        "什么是梯度下降", [_col()], top_k=2,
        vector_store=FakeVS(), embedder=FakeEmbedder(), llm=llm,
    )
    assert result.answer == llm.answer
    assert len(llm.calls) == 1
    assert result.citations  # 即使向量库为空，BM25 也应召回语料
    assert result.citations[0]["ref_no"] == 1
    assert "source" in result.citations[0] and "excerpt" in result.citations[0]


def test_rag_ask_citations_align_with_truncated_prompt():
    # 评审修复回归：max_chars 截断发生时，prompt 内编号必须与 citations 的 ref_no 严格一致。
    # 语料 6 块 × 约 831 字符（含头部），5 块 4155 > 4000，必然在第 5 块截断（前 4 块 3324）。
    # 每对相邻两块共享一个 df=2 的查询词：N=6 时 df=2 的词 IDF=log4.5-log2.5≈0.588>0，
    # 6 块全部 BM25 score>0（df=3 时 IDF 恰为 0，df≥4 为负，只有 df=1/2 才为正且安全）。
    filler = "内容" * 400  # 800 字符填充，凑足截断所需长度
    chunks = [
        Chunk(text=f"梯度下降。{filler}", kind="text", source="教材.pdf", page=1, id="c1"),
        Chunk(text=f"梯度下降。{filler}", kind="text", source="教材.pdf", page=2, id="c2"),
        Chunk(text=f"优化收敛。{filler}", kind="text", source="教材.pdf", page=3, id="c3"),
        Chunk(text=f"优化收敛。{filler}", kind="text", source="教材.pdf", page=4, id="c4"),
        Chunk(text=f"拟合迭代。{filler}", kind="text", source="教材.pdf", page=5, id="c5"),
        Chunk(text=f"拟合迭代。{filler}", kind="text", source="教材.pdf", page=6, id="c6"),
    ]
    col = KBCollection(name="kb", chunks=chunks)
    llm = FakeLLM()
    result = rag_ask(
        "梯度下降优化收敛拟合迭代", [col],
        vector_store=FakeVS(), embedder=FakeEmbedder(), llm=llm,
    )
    assert result.citations  # BM25 至少召回 3 块（实际 6 块全部 score>0）
    assert len(result.citations) < len(col.chunks)  # 超出 4000 预算，必然截断
    ref_nos = [c["ref_no"] for c in result.citations]
    assert ref_nos == list(range(1, len(ref_nos) + 1))  # 编号从 1 连续
    prompt_numbers = {
        int(m) for m in re.findall(r"\[(\d+)\] 来源", llm.calls[0][0]["content"])
    }
    assert prompt_numbers == set(ref_nos)  # prompt 内编号集合与 citations 严格对齐
```

（评审修复：新增 test_rag_ask_citations_align_with_truncated_prompt——原实现截断只作用于 prompt，citations 由全部 hits 推导，截断时 prompt 编号 [1..k] 与 citations [1..n] 错位、引用溯源失真；_col() 语料同步为实际 3 块版本）

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_rag_ask.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.rag_ask）

- [ ] **Step 3: 实现问答组装** `backend/app/services/rag_ask.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 问答组装：检索结果编号拼入提示词 → LLM 生成 → 返回带引用溯源的答案。"""
from dataclasses import dataclass, field

from .llm_gateway import get_gateway
from .rag import KBCollection, RagHit, hybrid_retrieve

PROMPT_SYSTEM = (
    "你是高职院校的教育智能助教。请基于【检索资料】回答学生的问题，"
    "回答时在引用资料处标注编号如[1][2]。若资料不足以回答，请明确说明。"
)


@dataclass
class RagAnswer:
    answer: str
    citations: list[dict] = field(default_factory=list)


def _select_hits(hits: list[RagHit], max_chars: int) -> list[tuple[int, RagHit]]:
    """按 max_chars 预算截断命中并编号，返回 (ref_no, hit) 列表。"""
    selected: list[tuple[int, RagHit]] = []
    total = 0
    for i, h in enumerate(hits, start=1):
        page = f" 第{h.chunk.page}页" if h.chunk.page is not None else ""
        block = f"[{i}] 来源:{h.chunk.source}{page} 类型:{h.chunk.kind}\n{h.chunk.text}"
        if total + len(block) > max_chars:
            break
        selected.append((i, h))
        total += len(block)
    return selected


def build_answer_prompt(question: str, hits: list[RagHit], max_chars: int = 4000) -> list[dict]:
    """把检索结果编号拼进 system prompt，超出长度截断。"""
    blocks = []
    for i, h in _select_hits(hits, max_chars):
        page = f" 第{h.chunk.page}页" if h.chunk.page is not None else ""
        blocks.append(f"[{i}] 来源:{h.chunk.source}{page} 类型:{h.chunk.kind}\n{h.chunk.text}")
    system = PROMPT_SYSTEM
    if blocks:
        system += "\n\n【检索资料】\n" + "\n\n".join(blocks)
    user = f"【问题】{question}\n要求：引用资料处标注编号如[1]；资料不足时说明。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def rag_ask(
    question: str,
    collections: list[KBCollection],
    top_k: int = 5,
    *,
    vector_store=None,
    embedder=None,
    llm=None,
) -> RagAnswer:
    """完整链路：混合检索 → 组装提示词 → LLM 生成 → 引用溯源。"""
    hits = hybrid_retrieve(question, collections, top_k, vector_store=vector_store, embedder=embedder)
    selected = _select_hits(hits, 4000)  # 与 prompt 同一编号切片，截断后引用不越界
    messages = build_answer_prompt(question, hits)
    chat = llm or get_gateway()
    answer = chat.chat(messages)
    citations = [
        {
            "ref_no": i,
            "source": h.chunk.source,
            "page": h.chunk.page,
            "kind": h.chunk.kind,
            "excerpt": h.chunk.text[:200],
            "image_path": h.chunk.meta.get("image_path"),
        }
        for i, h in selected
    ]
    return RagAnswer(answer=answer, citations=citations)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_rag_ask.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: RAG问答组装（检索编号+引用溯源）"
```

---

### Task 10: 前端骨架（Vue3 + Element Plus + 登录 + 布局）

**Files:**
- Create: `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`、`frontend/src/env.d.ts`、`frontend/src/main.ts`、`frontend/src/App.vue`、`frontend/src/router/index.ts`、`frontend/src/stores/auth.ts`、`frontend/src/api/http.ts`、`frontend/src/views/LoginView.vue`、`frontend/src/views/HomeView.vue`、`frontend/src/views/PlaceholderView.vue`

**Interfaces:**
- Consumes: 后端 `/api/auth/*`（Task 2）
- Produces: 前端路由 `/login`、`/`（Home，含四模块菜单占位）；`stores/auth.ts`（token/user/登录登出）；`api/http.ts`（axios 实例，自动带 token、统一错误提示、401 跳登录）。Plan B~E 直接在此骨架上加页面。

- [ ] **Step 1: 创建前端文件**（内容如下）

`frontend/package.json`：

```json
{
  "name": "edu-agent-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.7.0",
    "element-plus": "^2.9.0",
    "pinia": "^3.0.0",
    "vue": "^3.5.0",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.0",
    "typescript": "~5.6.0",
    "vite": "^6.0.0"
  }
}
```

`frontend/vite.config.ts`：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } }
  }
})
```

`frontend/tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "jsx": "preserve",
    "esModuleInterop": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src/**/*.ts", "src/**/*.vue"]
}
```

`frontend/index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>教育智能体平台</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`frontend/src/env.d.ts`：

```ts
/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
```

`frontend/src/main.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
```

`frontend/src/App.vue`：

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <router-view />
</template>
```

`frontend/src/api/http.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
// 注意：不 import router（避免 http→router→stores/auth→http 循环依赖），401 直接整页跳转登录
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    ElMessage.error(err.response?.data?.detail || '请求失败')
    if (err.response?.status === 401) window.location.href = '/login'
    return Promise.reject(err)
  }
)

export default http
```

`frontend/src/stores/auth.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import { defineStore } from 'pinia'
import http from '@/api/http'

interface User { id: number; username: string; role: string; real_name: string }

// 容错读取 localStorage 中的 user：存储值可能被手动编辑、写入截断或来自旧 schema，
// 直接 JSON.parse 抛异常会导致 store 初始化失败；useAuthStore() 被路由守卫（router/index.ts）
// 与 axios 拦截器（http.ts）调用，一旦抛出整个应用无法启动。解析失败时回退 null。
function loadUserFromStorage(): User | null {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null') as User | null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: loadUserFromStorage()
  }),
  actions: {
    async login(username: string, password: string) {
      const data = await http.post('/auth/login', { username, password }) as any
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', this.token)
      localStorage.setItem('user', JSON.stringify(this.user))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    }
  }
})
```

（评审修复：user 的 localStorage 读取包进 loadUserFromStorage() try/catch——原实现直接 JSON.parse，存储值损坏（手动编辑/写入截断/schema 迁移）时 store 初始化抛异常，而 useAuthStore() 被路由守卫与 axios 拦截器调用，会导致整个应用无法启动；解析失败回退 null）

`frontend/src/router/index.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue') },
    { path: '/', component: () => import('@/views/HomeView.vue') },
    { path: '/module/:name', component: () => import('@/views/PlaceholderView.vue') }
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.token) return '/login'
})

export default router
```

`frontend/src/views/LoginView.vue`：

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2>教育智能体平台</h2>
      <el-form :model="form" @keyup.enter="onLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="onLogin">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function onLogin() {
  if (!form.username || !form.password) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap { height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; }
.login-card { width: 380px; }
</style>
```

`frontend/src/views/HomeView.vue`：

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <el-container style="height: 100vh">
    <el-aside width="220px">
      <el-menu :default-active="$route.path" router background-color="#001529" text-color="#ccc" active-text-color="#fff">
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/module/prep">智能备课</el-menu-item>
        <el-menu-item index="/module/assistant">智能助教</el-menu-item>
        <el-menu-item index="/module/learn">个性化学习</el-menu-item>
        <el-menu-item index="/module/interview">面试AI复盘</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="display: flex; align-items: center; justify-content: space-between">
        <span>欢迎，{{ auth.user?.real_name || auth.user?.username }}</span>
        <el-button @click="onLogout">退出登录</el-button>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
function onLogout() { auth.logout(); router.push('/login') }
</script>
```

`frontend/src/views/PlaceholderView.vue`：

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <el-card>
    <h3>{{ title }}</h3>
    <el-empty :description="`${title} 建设中，后续工单将在此交付`" />
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const names: Record<string, string> = {
  prep: '智能备课（工单17）', assistant: '智能助教（工单18）',
  learn: '个性化学习（工单19）', interview: '面试AI复盘（工单20）'
}
const route = useRoute()
const title = computed(() => names[String(route.params.name)] || '模块')
</script>
```

- [ ] **Step 2: 安装依赖并构建验证**

Run: `cd frontend && npm install && npm run build`
Expected: 构建成功，无报错（`dist/` 生成）

- [ ] **Step 3: 端到端手动验证**

1. 启动后端：`cd backend && python -m uvicorn app.main:app --reload --port 8000`
2. 启动前端：`cd frontend && npm run dev`
3. 注册账号：`curl -X POST http://localhost:8000/api/auth/register -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123","role":"admin","real_name":"管理员"}'`
Expected: `{"username":"admin",...}`
4. 浏览器打开 `http://localhost:5173`，用 admin/admin123 登录
Expected: 跳转首页，左侧显示五个菜单，点"智能备课"等显示"建设中"占位页；直接访问 `/login` 之外的页面未登录时自动跳登录页

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: 前端骨架（Vue3+Element Plus+登录+四模块布局）"
```

---

### Task 11: 工单 16 —— 教育智能体需求分析与软件架构设计文档

**Files:**
- Create: `docs/工单16-教育智能体需求分析与软件架构设计.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-09-14-edu-agent-platform-design.md`（设计文档即素材）
- Produces: 工单 16 验收文档（七章结构，验收标准：内容符合高职院校核心痛点及 AIGC 主流技术方案选型要求）

- [ ] **Step 1: 撰写第一~三章**（一、项目背景；二、需求分析；三、软件设计架构）

内容要点：
- **一、项目背景**：政策与行业驱动（《职业教育信息化2.0行动计划》等）、高职教育痛点（教师备课负担重/学生基础差异大/行政流程低效/面试就业数据缺失）、技术成熟度（大模型/Agent/多模态/数据整合）——素材见工单16原文
- **二、需求分析**：
  - 目标用户：教师/学生/校务管理者（含就业指导），每类用户的核心痛点与诉求（表格）
  - 主要功能场景：教学侧（智能备课/智能助教/教学评估/个性化学习）+ 管理侧（教务管理助手/简历投递与面试跟踪），对照本项目四个模块（工单17~20）给出功能清单与验收标准映射
- **三、软件设计架构**：
  - 总体架构：四层架构图（前端层 Vue3 / 后端层 FastAPI / 智能服务层 LLM网关+RAG引擎+解析管线+ASR+画像推荐 / 数据层 SQLite+Milvus+Neo4j+文件存储）——直接用设计文档"第 3 节 总体架构"内容
  - 详细分层说明：每层的职责、组件清单、模块间接口关系（文字 + ASCII 图）

- [ ] **Step 2: 撰写第四章**（各场景技术选型分析）

内容要点：按场景列表格（场景 / 技术选型 / 选型理由 / 备选方案）：
- 内容生成（DeepSeek chat + JSON 模式，备选 Qwen/GPT-4）
- 检索增强 RAG（bge-m3 本地向量化 + Milvus Lite/FAISS + BM25 混合检索 + RRF/bge-reranker 重排，备选 Elasticsearch）
- 多模态文档解析（PyMuPDF/python-docx/python-pptx/openpyxl + RapidOCR(PaddleOCR 模型)，参考 RAG-Anything 思路）
- 语音识别（FunASR paraformer-zh，备选云 API）
- 个性化推荐（Neo4j 知识图谱 + 协同过滤 numpy 实现 + 画像时间衰减）
- 面试复盘（FunASR + DeepSeek 结构化评分 JSON）
- 前端（Vue3 + Element Plus + wangeditor）

- [ ] **Step 3: 撰写第五~六章**（数据安全与合规；实施建议）

内容要点：
- **五、数据安全与合规**：JWT 认证与角色权限（RBAC）、私有知识库数据隔离（按 owner 过滤）、密码 bcrypt 哈希、上传文件类型白名单、数据加密存储与本地化部署能力、《数据安全法》《个人信息保护法》合规要点（面试录音等敏感数据脱敏与权限控制）
- **六、实施建议**：资源规划（1 台开发机即可：CPU 跑 bge-m3/FunASR/OCR；DeepSeek API 按量付费预算约 ¥10/月）+ 9 人日工时安排表（对应 D1~D14 排期）+ 团队分工建议 + 里程碑

- [ ] **Step 4: 对照工单验收标准自检**

逐项核对工单16"产出物"清单：
- ✅ 一、项目背景 / 二、需求分析（目标用户、主要功能场景）/ 三、软件设计架构（总体架构、详细分层说明）/ 四、各场景技术选型分析 / 五、数据安全与合规 / 六、实施建议（资源规划及工时安排）
- ✅ 内容贴合高职院校用户核心痛点，技术选型均为 AIGC 主流方案（RAG/Agent/知识图谱/ASR）
Expected: 七章结构完整，无缺项

- [ ] **Step 5: 提交**

```bash
git add docs/工单16-教育智能体需求分析与软件架构设计.md && git commit -m "docs: 工单16 教育智能体需求分析与软件架构设计文档"
```

---

### Task 12: 演示数据 + 环境模板 + README（底座收尾）

**Files:**
- Create: `backend/scripts/seed_demo_data.py`、`backend/.env.example`、根目录 `README.md`

**Interfaces:**
- Consumes: 全部底座组件（auth/文件/解析）
- Produces: 预置账号与人工智能课程演示数据（Plan B~E 直接使用）；项目启动文档

- [ ] **Step 1: 写演示数据脚本** `backend/scripts/seed_demo_data.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""演示数据脚本：预置 4 类角色账号 + 人工智能课程样例文档。
用法：cd backend && python -m scripts.seed_demo_data
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pymupdf import open as open_pdf

from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models.user import Role, User

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"

USERS = [
    ("admin", "admin123", Role.admin, "管理员"),
    ("teacher", "teacher123", Role.teacher, "王老师"),
    ("student", "student123", Role.student, "李同学"),
    ("counselor", "counselor123", Role.counselor, "张指导"),
]


def seed_users(db) -> None:
    for username, pwd, role, name in USERS:
        if not db.query(User).filter(User.username == username).first():
            db.add(User(username=username, hashed_password=hash_password(pwd), role=role, real_name=name))
    db.commit()


def make_demo_files() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    # 1) 讲义 docx
    doc = Document()
    doc.add_heading("人工智能导论讲义", level=1)
    doc.add_heading("第3章 机器学习基础", level=2)
    doc.add_paragraph("梯度下降是机器学习中最基础的优化算法。它通过沿损失函数负梯度方向迭代更新参数，逐步逼近最优解。学习率控制每次更新的步长。")
    doc.add_paragraph("线性回归通过拟合一条直线描述特征与目标值之间的关系，常用于房价预测等连续值预测场景。")
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "算法"; table.cell(0, 1).text = "适用场景"
    table.cell(1, 0).text = "线性回归"; table.cell(1, 1).text = "房价预测"
    table.cell(2, 0).text = "逻辑回归"; table.cell(2, 1).text = "二分类"
    doc.save(DEMO_DIR / "人工智能导论讲义.docx")
    # 2) 课件 pptx
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "机器学习基础"
    slide.placeholders[1].text = "主讲：王老师"
    slide2 = prs.slides.add_slide(prs.slide_layouts[1])
    slide2.shapes.title.text = "梯度下降"
    slide2.placeholders[1].text = "沿负梯度方向迭代更新参数"
    prs.save(DEMO_DIR / "机器学习课件.pptx")
    # 3) 试题 xlsx
    wb = Workbook()
    ws = wb.active
    ws.append(["题干", "选项A", "选项B", "选项C", "选项D", "答案", "知识点", "难度"])
    ws.append(["梯度下降中控制步长的参数是", "学习率", "批量大小", "迭代次数", "正则系数", "A", "梯度下降", "易"])
    ws.append(["以下哪个算法适合房价预测", "线性回归", "K-means", "决策树分类", "PCA", "A", "线性回归", "易"])
    wb.save(DEMO_DIR / "诊断试题.xlsx")
    # 4) 教材 pdf
    pdf_doc = open_pdf()
    page = pdf_doc.new_page()
    page.insert_text((72, 72), "人工智能导论：机器学习基础\n梯度下降通过迭代更新参数逼近最优解。")
    pdf_doc.save(DEMO_DIR / "人工智能导论教材.pdf")
    pdf_doc.close()
    print("演示文件已生成：", DEMO_DIR)


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_users(db)
        make_demo_files()
        print("演示账号：admin/admin123(管理员) teacher/teacher123(教师) student/student123(学生) counselor/counselor123(就业指导)")
    finally:
        db.close()
```

- [ ] **Step 2: 写环境模板与 README**

`backend/.env.example`：

```
# 复制为 backend/.env 后填写
DEEPSEEK_API_KEY=sk-你的key
# EMBEDDING_MODEL=BAAI/bge-m3
# VECTOR_BACKEND=milvus   # milvus | faiss（Milvus 跑不起来时改 faiss）
# HF_ENDPOINT=https://hf-mirror.com   # 模型下载慢时启用（在启动后端前设置环境变量）
```

根目录 `README.md`：

```markdown
# edu-agent-platform 教育智能体平台

Agent 数字人项目-教育智能体方向实训（工单 16~20）。单体平台四层架构：Vue3 + FastAPI + 智能服务层 + 数据层。

## 快速启动

### 后端（端口 8000）
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY
python -m scripts.seed_demo_data   # 预置账号与演示数据
python -m uvicorn app.main:app --reload --port 8000

### 前端（端口 5173）
cd frontend
npm install
npm run dev

浏览器打开 http://localhost:5173 ，账号：admin/admin123（管理员）、teacher/teacher123（教师）、student/student123（学生）、counselor/counselor123（就业指导）

## 测试
cd backend && pytest          # 单元测试（不含 smoke）
cd backend && pytest -m smoke -o addopts=""   # 冒烟测试（需已下载 bge-m3 等模型）

## 工单对照
| 工单 | 模块 | 状态 |
|---|---|---|
| 16 | 需求分析与软件架构设计 | ✅ docs/工单16-教育智能体需求分析与软件架构设计.md |
| 17 | 智能备课 | Plan B |
| 18 | 智能助教（多模态RAG） | Plan C |
| 19 | 个性化学习推荐 | Plan D |
| 20 | 面试AI复盘 | Plan E |

## 目录结构
backend/app/{api,core,models,services} 后端分层
frontend/src/{api,router,stores,views} 前端
docs/ 工单文档与设计/计划
```

- [ ] **Step 3: 运行演示数据脚本验证**

Run: `cd backend && python -m scripts.seed_demo_data`
Expected: 打印"演示文件已生成：...data\demo"，账号创建成功；`backend/data/demo/` 下出现 4 个文件

- [ ] **Step 4: 全量测试回归**

Run: `cd backend && pytest -v`
Expected: 全部 PASS（test_health 1 + test_auth 5 + test_llm_gateway 7 + test_file_service 5 + test_parser 7 + test_vector_store 4 + test_rag 4 + test_rag_ask 2 = 35 passed，smoke 自动跳过）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 演示数据脚本+环境模板+README（底座收尾，工单16-20）"
```

---

## 完成标准（Plan A）

- [ ] 后端 35 个测试全部通过；smoke（bge-m3/Milvus）可跑通或已配置 FAISS 兜底
- [ ] 登录注册闭环可用（curl + 浏览器验证）
- [ ] 解析管线对 PDF/DOCX/PPTX/XLSX/图片产出多模态 Chunk（测试覆盖）
- [ ] 混合检索 + RRF 重排 + rag_ask 引用溯源可用（测试覆盖）
- [ ] 工单 16 文档七章齐全
- [ ] README 启动步骤可复现；演示账号可登录
- [ ] 每个任务已单独 commit
