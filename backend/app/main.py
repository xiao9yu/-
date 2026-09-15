# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import auth, files
from .core.exceptions import register_exception_handlers
from .db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # 启动时建表（实训简化，不引入 Alembic）
    yield


app = FastAPI(title="edu-agent-platform", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
