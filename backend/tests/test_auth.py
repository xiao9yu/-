# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.user import User


def _register(client, username="stu1", role="student"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": "pass123456", "role": role, "real_name": "张三"},
    )


def _make_token(sub, exp):
    """用应用密钥签发 token，模拟持有合法签名的恶意/过期凭据。"""
    return jwt.encode({"sub": sub, "exp": exp}, settings.secret_key, algorithm="HS256")


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


def test_forged_non_numeric_sub_token_401(client):
    # 合法签名但 sub 非数字的 token：坏凭据，必须 401 而非 500
    token = _make_token("abc", datetime.now(timezone.utc) + timedelta(minutes=5))
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_expired_token_401(client):
    token = _make_token("1", datetime.now(timezone.utc) - timedelta(minutes=5))
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_deleted_user_token_401(client, tmp_path):
    _register(client)
    token = client.post(
        "/api/auth/login", json={"username": "stu1", "password": "pass123456"}
    ).json()["access_token"]

    # 直接从测试库删除该用户（模拟账号被删除后旧 token 访问，走"用户不存在"分支）
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.query(User).filter(User.username == "stu1").delete()
        db.commit()

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
