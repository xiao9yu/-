# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import BizError, register_exception_handlers
from app.main import app


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_app_startup_lifespan(tmp_path, monkeypatch):
    """回归测试：真实 lifespan 启动（建表）不能因 data/ 目录缺失而崩溃。"""
    # 双保险隔离：conftest 已把 settings.db_url 指向会话临时目录；
    # 再切 CWD，防止任何按 CWD 解析的路径写回 backend/data/
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/health").json() == {"status": "ok"}


def test_biz_error_returns_structured_json():
    """BizError 应返回携带中文提示的结构化错误 JSON。"""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/api/boom")
    def boom():
        raise BizError(status_code=403, message="没有权限")

    @test_app.get("/api/crash")
    def crash():
        raise RuntimeError("kaboom")

    c = TestClient(test_app, raise_server_exceptions=False)
    resp = c.get("/api/boom")
    assert resp.status_code == 403
    assert resp.json() == {"detail": "没有权限"}

    resp = c.get("/api/crash")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "服务器内部错误"}
