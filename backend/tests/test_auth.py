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
