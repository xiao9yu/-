# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""数据库引擎与会话。SQLite 开发期，SQLAlchemy 模型即数据库设计产出物。"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_is_sqlite = settings.db_url.startswith("sqlite")
if _is_sqlite:
    # SQLite 不会自动创建父目录，先确保 data/ 存在，否则启动建表直接报错
    Path(settings.db_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
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
