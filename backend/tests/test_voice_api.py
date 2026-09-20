# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""数字人语音 API 测试：WS 鉴权/全链路/打断/占线/降级（全 mock，不加载真实模型）。"""
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.db import Base
from app.main import app
from app.api import deps, voice
from app.models.user import Role, User
from app.services import kb_service
from app.services.asr_service import ASRUnavailableError


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


class FakeStore:
    def create_collection(self, name, dim): pass
    def upsert(self, name, ids, vectors, metadatas): pass

    def search(self, name, query_vector, top_k, filter_dict=None):
        return []

    def delete(self, name, ids): pass


class FakeGateway:
    def chat_stream(self, messages, temperature=0.7):
        yield "什么是梯度下降？"
        yield "学习率很关键。"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时 DB + 假向量库/嵌入模型 + student token + TestClient。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'voice.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: FakeStore())
    monkeypatch.setattr(kb_service, "get_gateway", lambda: FakeGateway())
    from app.api import kb as kb_api
    monkeypatch.setattr(kb_api, "get_reranker", lambda: None)
    from app.core.security import create_access_token, hash_password
    s = Session()
    u = User(username="stu", hashed_password=hash_password("p"), role=Role.student, real_name="stu")
    s.add(u)
    s.commit()
    s.refresh(u)
    token = create_access_token(u.id, u.role.value)
    s.close()
    from fastapi.testclient import TestClient
    yield TestClient(app), token
    app.dependency_overrides.clear()


def _auth(ws, token):
    ws.send_json({"type": "auth", "token": token})
    assert ws.receive_json() == {"type": "status", "state": "ready"}


def test_ws_auth_required(env):
    client, _ = env
    with client.websocket_connect("/api/voice/chat") as ws:
        ws.send_json({"type": "audio", "data": "eA=="})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "auth" in msg["message"]
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()  # 服务端已 close(4401)


def test_ws_voice_full_flow(env, monkeypatch):
    client, token = env
    monkeypatch.setattr(voice, "transcribe", lambda wav: "什么是梯度下降")
    monkeypatch.setattr("app.services.tts_service._communicate",
                        lambda text, v: ("mp3-" + text).encode("utf-8"))
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        msgs = []
        while True:
            m = ws.receive_json()
            msgs.append(m)
            if m["type"] == "done":
                break
    # 边生成边播：句末标点落句即合成——audio 与 delta 交错
    assert [m["type"] for m in msgs] == [
        "status", "transcript", "status", "citations", "delta", "audio", "delta", "audio", "done"
    ]
    assert msgs[0] == {"type": "status", "state": "transcribing"}
    assert msgs[1] == {"type": "transcript", "text": "什么是梯度下降"}
    assert msgs[4] == {"type": "delta", "text": "什么是梯度下降？"}
    assert "".join(m["text"] for m in msgs if m["type"] == "delta") == "什么是梯度下降？学习率很关键。"
    assert msgs[-1] == {"type": "done", "audio_total": 2}
    import base64
    assert base64.b64decode(msgs[5]["data"]) == "mp3-什么是梯度下降？".encode("utf-8")
    assert base64.b64decode(msgs[7]["data"]) == "mp3-学习率很关键。".encode("utf-8")


def test_ws_cancel_stops_pipeline(env, monkeypatch):
    client, token = env

    def slow_transcribe(wav):
        time.sleep(0.3)
        return "什么是梯度下降"

    monkeypatch.setattr(voice, "transcribe", slow_transcribe)
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        assert ws.receive_json() == {"type": "status", "state": "transcribing"}
        ws.send_json({"type": "cancel"})
        assert ws.receive_json() == {"type": "status", "state": "cancelled"}


def test_ws_busy_rejects_second_audio(env, monkeypatch):
    client, token = env

    def slow_transcribe(wav):
        time.sleep(0.3)
        return "问题"

    monkeypatch.setattr(voice, "transcribe", slow_transcribe)
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"type": "audio", "data": "eA=="})
        assert "正在处理中" in ws.receive_json()["message"]
        # 偏离简报：打断并收尾，让慢转写线程在 WS 会话内结束（否则测试退出后线程
        # 回调已关闭的事件循环抛 RuntimeError，全量输出不干净）
        ws.send_json({"type": "cancel"})
        assert ws.receive_json() == {"type": "status", "state": "cancelled"}


def test_ws_asr_unavailable(env, monkeypatch):
    client, token = env

    def boom(wav):
        raise ASRUnavailableError("语音识别未就绪，请打字提问")

    monkeypatch.setattr(voice, "transcribe", boom)
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        # 偏离简报：流水线先发 status(transcribing)（设计文档 §5 事件序，全链路测试 msgs[0] 同），再发 error
        assert ws.receive_json() == {"type": "status", "state": "transcribing"}
        m = ws.receive_json()
        assert m["type"] == "error"
        assert "语音识别未就绪" in m["message"]


def test_ws_empty_transcript(env, monkeypatch):
    client, token = env
    monkeypatch.setattr(voice, "transcribe", lambda wav: "")
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        # 偏离简报：同上，先消费 status(transcribing)
        assert ws.receive_json() == {"type": "status", "state": "transcribing"}
        m = ws.receive_json()
        assert m["type"] == "error"
        assert "未识别到语音" in m["message"]


def test_tts_requires_auth(env):
    client, _ = env
    resp = client.post("/api/voice/tts", json={"text": "你好"})
    assert resp.status_code == 401


def test_tts_returns_mp3(env, monkeypatch):
    client, token = env
    monkeypatch.setattr("app.services.tts_service._communicate", lambda t, v: b"mp3-bytes")
    resp = client.post("/api/voice/tts", json={"text": "你好"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.content == b"mp3-bytes"
    assert resp.headers["content-type"] == "audio/mpeg"


def test_tts_empty_text(env):
    client, token = env
    resp = client.post("/api/voice/tts", json={"text": "   "},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


def test_tts_unavailable_returns_502(env, monkeypatch):
    client, token = env
    # 偏离简报：tts_service 模块级 LRU 缓存会命中上一用例缓存的"你好"，
    # 先清缓存，确保真正走到 _communicate 失败路径（否则 200 而非 502）
    from app.services import tts_service
    tts_service._cache.clear()

    def boom(t, v):
        raise RuntimeError("网络失败")

    monkeypatch.setattr("app.services.tts_service._communicate", boom)
    resp = client.post("/api/voice/tts", json={"text": "你好"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 502
