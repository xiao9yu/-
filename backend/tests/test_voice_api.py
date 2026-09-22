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


@pytest.fixture(autouse=True)
def clear_tts_cache():
    """TTS 模块级 LRU 缓存跨用例存活：同一句文本在多个用例里被 patch 成不同 mp3，
    不清缓存会让后跑的用例读到前一个用例的字节（假通过/假失败）。"""
    from app.services import tts_service
    tts_service._cache.clear()
    tts_service._timed_cache.clear()
    yield
    tts_service._cache.clear()
    tts_service._timed_cache.clear()


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
    # 口型时间轴改造后，语音链路走 synthesize_timed（seam 为 _communicate_timed）；
    # 打字朗读 /tts 仍走 synthesize（seam 为 _communicate），两条路径互不影响
    monkeypatch.setattr("app.services.tts_service._communicate_timed",
                        lambda text, v: (("mp3-" + text).encode("utf-8"), []))
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        msgs = []
        while True:
            m = ws.receive_json()
            msgs.append(m)
            if m["type"] == "done":
                break
    # 边生成边播：句末标点落句即合成——audio 与 delta 交错；
    # session 事件在 transcript 之后：多轮模式下前端据此拿到会话 id 续接上下文
    assert [m["type"] for m in msgs] == [
        "status", "transcript", "session", "status", "citations",
        "delta", "audio", "delta", "audio", "done"
    ]
    assert msgs[0] == {"type": "status", "state": "transcribing"}
    assert msgs[1] == {"type": "transcript", "text": "什么是梯度下降"}
    assert msgs[2]["type"] == "session" and msgs[2]["turns"] == 0
    assert msgs[5] == {"type": "delta", "text": "什么是梯度下降？"}
    assert "".join(m["text"] for m in msgs if m["type"] == "delta") == "什么是梯度下降？学习率很关键。"
    assert msgs[-1] == {"type": "done", "audio_total": 2}
    import base64
    assert base64.b64decode(msgs[6]["data"]) == "mp3-什么是梯度下降？".encode("utf-8")
    assert base64.b64decode(msgs[8]["data"]) == "mp3-学习率很关键。".encode("utf-8")
    # 音频事件带口型时间轴字段（TTS 未下发边界时为空列表，前端退回音量驱动）
    assert msgs[6]["marks"] == []


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


# ---------- 口型时间轴（打字朗读路径） ----------
def test_tts_timed_returns_audio_and_marks(env, monkeypatch):
    client, token = env
    import base64
    monkeypatch.setattr("app.services.tts_service._communicate_timed",
                        lambda t, v: (b"mp3", [{"text": "你", "t0": 0.0, "t1": 0.25}]))
    resp = client.post("/api/voice/tts/timed", json={"text": "你好"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert base64.b64decode(body["audio"]) == b"mp3"
    assert body["marks"] == [{"text": "你", "t0": 0.0, "t1": 0.25}]


def test_tts_timed_requires_auth_and_validates_text(env):
    client, token = env
    assert client.post("/api/voice/tts/timed", json={"text": "你好"}).status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/voice/tts/timed", json={"text": "  "}, headers=headers).status_code == 400
    assert client.post("/api/voice/tts/timed", json={"text": "啊" * 2001},
                       headers=headers).status_code == 400


# ---------- 流式自然对话 ----------
def test_capabilities_reports_stream_availability(env, monkeypatch):
    client, token = env
    from app.services import asr_stream
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(asr_stream, "available", lambda: False)
    assert client.get("/api/voice/capabilities", headers=headers).json() == {
        "stream": False, "push_to_talk": True, "tts": True}
    monkeypatch.setattr(asr_stream, "available", lambda: True)
    assert client.get("/api/voice/capabilities", headers=headers).json()["stream"] is True


def test_capabilities_requires_auth(env):
    client, _ = env
    assert client.get("/api/voice/capabilities").status_code == 401


class _FakeRecognizer:
    """按第 n 帧产出脚本事件：模拟 VAD 端点 + 增量转写。"""

    def __init__(self):
        self.n = 0

    def feed(self, pcm):
        self.n += 1
        if self.n == 1:
            return [("partial", {"text": "什么是"})]
        if self.n == 2:
            return [("segment_end", {"text": "什么是梯度下降", "duration_ms": 900})]
        return []

    def finish(self):
        return []


def test_ws_stream_segment_flow_and_session(env, monkeypatch):
    """流式模式：partial 上屏 → 端点命中出整段回答 → segment_done → 回到 listening。"""
    client, token = env
    import base64
    from app.services import asr_stream
    monkeypatch.setattr(asr_stream, "available", lambda: True)
    monkeypatch.setattr(asr_stream, "StreamingRecognizer", _FakeRecognizer)
    monkeypatch.setattr("app.services.tts_service._communicate_timed",
                        lambda t, v: (b"mp3", [{"text": "x", "t0": 0.0, "t1": 0.1}]))
    chunk = base64.b64encode(b"\x00\x00" * 320).decode("ascii")
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "stream_start"})
        assert ws.receive_json() == {"type": "status", "state": "listening"}
        ws.send_json({"type": "stream_chunk", "data": chunk})
        assert ws.receive_json() == {"type": "partial", "text": "什么是"}
        ws.send_json({"type": "stream_chunk", "data": chunk})
        got = []
        while True:
            m = ws.receive_json()
            got.append(m)
            if m["type"] == "status" and m["state"] == "listening":
                break
        kinds = [m["type"] for m in got]
        assert kinds[0] == "transcript" and got[0]["text"] == "什么是梯度下降"
        assert "session" in kinds              # 会话凭据随段落下发
        assert "citations" in kinds and "segment_done" in kinds
        assert kinds[-1] == "status"
        ws.send_json({"type": "stream_end"})
        assert ws.receive_json() == {"type": "status", "state": "ready"}


def test_ws_stream_start_rejected_when_unavailable(env, monkeypatch):
    client, token = env
    from app.services import asr_stream
    monkeypatch.setattr(asr_stream, "available", lambda: False)
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "stream_start"})
        m = ws.receive_json()
        assert m["type"] == "error" and "按住说话" in m["message"]


def test_ws_unknown_message_type_errors(env):
    client, token = env
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "nonsense"})
        assert ws.receive_json()["type"] == "error"


def test_ws_second_turn_reuses_session(env, monkeypatch):
    """多轮：第二轮带 session_id 续接同一会话，turns 递增（语音与文字共享上下文）。"""
    client, token = env
    monkeypatch.setattr(voice, "transcribe", lambda wav: "那学习率呢")
    monkeypatch.setattr("app.services.tts_service._communicate_timed",
                        lambda t, v: (b"mp3", []))
    with client.websocket_connect("/api/voice/chat") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json() == {"type": "status", "state": "ready"}
        ws.send_json({"type": "audio", "data": "eA=="})
        first = None
        while True:
            m = ws.receive_json()
            if m["type"] == "session":
                first = m
            if m["type"] == "done":
                break
        assert first is not None and first["turns"] == 0
        # 第二帧用同一个 WS（holder 已持会话）→ turns 应为 1
        ws.send_json({"type": "audio", "data": "eA=="})
        second = None
        while True:
            m = ws.receive_json()
            if m["type"] == "session":
                second = m
            if m["type"] == "done":
                break
        assert second is not None and second["id"] == first["id"] and second["turns"] == 1
