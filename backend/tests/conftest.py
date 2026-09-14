# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# 测试隔离：必须在导入 app.db（创建 engine）之前，把全局数据库指向会话临时目录。
# SQLAlchemy 在 create_engine 时即锁定 SQLite 相对路径（连接时不再按 CWD 解析），
# 若用默认的 sqlite:///./data/app.db，lifespan 建表会写进真实配置的 backend/data/app.db。
# nested/data 两级目录初始不存在，同时回归验证 db.py 的 SQLite 父目录自建逻辑。
_session_tmp = Path(tempfile.mkdtemp(prefix="edu-agent-tests-"))
settings.db_url = f"sqlite:///{_session_tmp / 'nested' / 'data' / 'app.db'}"

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


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
