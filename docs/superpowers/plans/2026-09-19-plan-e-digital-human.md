# Plan E：数字人交互（智能助教内嵌）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在智能助教页内嵌 Live2D 数字人：按住说话 → FunASR 本地转写 → 走既有 RAG 问答链 → edge-tts 分句合成 → 逐句播放 + 音量驱动口型；打字提问的回答也由数字人朗读（可静音）；支持一键打断。工单20 已取消（79c7d26），语音能力并入工单18。

**Architecture:** 后端全语音链路 + WebSocket 双工：前端 MediaRecorder 采集 webm → 浏览器内重编码 16k 单声道 WAV → WS 上行 → FunASR（paraformer-zh，modelscope 已可达，懒加载 + lifespan 预热）→ 复用 kb_service 事件流（重构出 answer_events）→ edge-tts 分句合成 → WS 逐句下行 mp3 → AudioContext 播放 + AnalyserNode 音量驱动 Live2D 口型；打断 = 前端停播 + WS cancel。打字模式复用既有 SSE，done 后走 HTTP /api/voice/tts 朗读。设计文档：docs/superpowers/specs/2026-09-19-digital-human-assistant-design.md。

**Tech Stack:** FastAPI（WS/HTTP）+ funasr paraformer-zh（torch 2.13 已装）+ edge-tts + Vue3/pixi.js@7/pixi-live2d-display/Live2D 官方免费样例模型（Hiyori）。

## Global Constraints

- 本计划所有新 Python 文件头部注释：`# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)`；Vue/TS 文件模板内 `<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展) -->`，script 内 `// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)`
- 代码注释用中文；每个任务结束必须 git commit（身份 `huqiaoyu <huqiaoyu@local>`，用 `git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit ...`；显式路径 `git add`，**绝不 `git add -A`**——仓库根有无关未跟踪文件"实训日报-七天.md"）；提交在 dev 分支（控制器已建，当前 HEAD 107c431）
- TDD：后端每个任务先写失败测试→跑测试确认失败→实现→跑测试确认通过→提交；pytest 从 `backend/` 目录运行（`python -m pytest`），默认排除 smoke
- 前端不写单测，以 `npm run build` 通过 + `npx tsc --noEmit` 0 错误验证
- **子代理不指定 model**（Anthropic API 402 余额不足，2026-09-18 教训）——派单时继承主会话模型
- **前端 Task 6/7 实现者**：默认控制器直接实现（Plan D Task 7 先例：用户改口"你直接做"）；派单前先与用户确认
- 绝不碰 `LoginView.vue` 与用户可能正在编辑的前端文件（派单前查 git status 核对）
- 本机 HF 不可达（代码级自动离线不变）；funasr 走 modelscope（已验证可达），**绝不触发 HF 下载**；`disable_update=True`
- 网络事实（2026-09-19 实测）：modelscope / PyPI / edge-tts 端点可达；edge-tts 属在线服务——所有 TTS 失败路径静默降级（回答文字不受影响）
- config 新增字段（逐字）：`asr_model: str = "paraformer-zh"`、`tts_voice: str = "zh-CN-XiaoxiaoNeural"`
- WS 协议逐字按设计文档 §5；音频格式：上行 16k 单声道 WAV、下行 mp3；后端零 ffmpeg 依赖（前端 OfflineAudioContext 重采样）
- 依赖版本：Python `funasr>=1.2`、`torchaudio>=2.13`（匹配已装 torch 2.13.0）、`edge-tts>=7.0`；npm `pixi.js@^7.4.2`、`pixi-live2d-display@^0.4.0`（**pixi.js v8 不兼容 pixi-live2d-display，禁装 v8**）
- Live2D 版权：Hiyori 为 Live2D 官方样例（Live2D Free Material License，可商用演示）；README 保留版权声明；不得替换为未授权模型
- 权限：语音接口登录即可用（复用智能助教口径，师生同权），无新角色
- 真实 DeepSeek key 只在 gitignored backend/.env，输出中要掩码
- 全量回归基线：153 passed, 2 deselected（Plan D 合并后）；本计划新增测试后需 ≥ 基线 + 新增
- 台账 .superpowers/sdd/progress.md：每任务完成后控制器追加一行进度记录（gitignored，恢复地图）

---

### Task 1: ASR 服务（FunASR 离线转写 + 依赖钉版）

**Files:**
- Create: `backend/app/services/asr_service.py`
- Create: `backend/tests/test_asr_service.py`
- Create: `backend/scripts/download_funasr_model.py`
- Modify: `backend/app/config.py`（新增 asr_model 字段）
- Modify: `backend/requirements.txt`（新增 funasr、torchaudio）

**Interfaces:**
- Consumes: `app.config.settings`（Plan A）
- Produces（Task 4 依赖，逐字签名）：
  - `asr_service.get_asr()` → `model | None`（懒加载单例；加载失败缓存 None 哨兵，仿 rerank get_reranker）
  - `asr_service.transcribe(wav_bytes: bytes) -> str`（16k 单声道 WAV 字节 → 转写文本；模型未就绪抛 `ASRUnavailableError`；未识别到语音返回 `""`）
  - `asr_service.ASRUnavailableError(Exception)`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_asr_service.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""ASR 服务测试：模型懒加载/失败哨兵/转写（全部 mock，不加载真实 funasr）。"""
import pytest

from app.services import asr_service


class FakeModel:
    """funasr AutoModel 替身：generate 返回其构造时固定的结果。"""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate(self, input=None):
        self.calls.append(input)
        return [{"text": self.text}]


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    """每个用例重置模块级单例状态。"""
    monkeypatch.setattr(asr_service, "_model", None)
    monkeypatch.setattr(asr_service, "_loaded", False)


def test_transcribe_returns_text(monkeypatch):
    monkeypatch.setattr(asr_service, "_load_model", lambda: FakeModel("  你好世界  "))
    assert asr_service.transcribe(b"wav-bytes") == "你好世界"


def test_transcribe_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(asr_service, "_load_model", lambda: FakeModel(""))
    assert asr_service.transcribe(b"wav-bytes") == ""


def test_model_load_failure_caches_none_and_raises(monkeypatch):
    def boom():
        raise RuntimeError("模型下载失败")

    monkeypatch.setattr(asr_service, "_load_model", boom)
    with pytest.raises(asr_service.ASRUnavailableError):
        asr_service.transcribe(b"wav-bytes")
    assert asr_service.get_asr() is None  # 失败哨兵已缓存，不再重试加载


def test_model_loaded_once(monkeypatch):
    calls = []

    def load():
        calls.append(1)
        return FakeModel("你好")

    monkeypatch.setattr(asr_service, "_load_model", load)
    asr_service.transcribe(b"a")
    asr_service.transcribe(b"b")
    assert len(calls) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_asr_service.py -v`
Expected: 全部 FAIL（`ModuleNotFoundError: app.services.asr_service`）

- [ ] **Step 3: 写最小实现**

`backend/app/services/asr_service.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""ASR 服务：本地 FunASR（paraformer-zh）离线语音转写。

懒加载单例 + lifespan 预热（main.py），失败缓存 None 哨兵：模型未下载/加载失败时
语音输入提示打字，文字功能零影响。funasr 经 modelscope 取模型（本机 HF 不可达），
disable_update=True 不联网检查更新。
"""
import logging
import threading

from ..config import settings

logger = logging.getLogger("asr")

_model = None       # AutoModel 实例；加载失败缓存 None 哨兵
_loaded = False
_lock = threading.Lock()


class ASRUnavailableError(Exception):
    """ASR 模型未就绪（未下载/加载失败）。"""


def _load_model():
    """加载 FunASR 模型（测试 monkeypatch 的 seam；真实 funasr 仅在此懒导入）。"""
    from funasr import AutoModel
    return AutoModel(model=settings.asr_model, disable_update=True)


def get_asr():
    """懒加载单例：成功缓存模型，失败缓存 None 哨兵（仿 rerank get_reranker）。"""
    global _model, _loaded
    with _lock:
        if not _loaded:
            _loaded = True
            try:
                _model = _load_model()
                logger.info("ASR 模型加载完成（%s）", settings.asr_model)
            except Exception as exc:
                _model = None
                logger.warning("ASR 模型加载失败（语音输入将提示打字）：%s", exc)
        return _model


def transcribe(wav_bytes: bytes) -> str:
    """16k 单声道 WAV 字节 → 转写文本。模型未就绪抛 ASRUnavailableError；空结果返回 ""。"""
    model = get_asr()
    if model is None:
        raise ASRUnavailableError("语音识别未就绪，请打字提问")
    results = model.generate(input=wav_bytes)
    if not results:
        return ""
    return str(results[0].get("text") or "").strip()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_asr_service.py -v`
Expected: 4 passed

- [ ] **Step 5: 钉依赖与配置 + 预下载脚本**

`backend/requirements.txt` 末尾追加：

```
funasr>=1.2
torchaudio>=2.13
```

`backend/app/config.py` 的 Settings 类"向量与模型"段后追加：

```python
    # 数字人语音
    asr_model: str = "paraformer-zh"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
```

（`tts_voice` 属 Task 2，此处一并落位，Task 2 不再改 config。）

安装依赖（torch 2.13.0 已装，pip 不会重复下载）：

Run: `cd backend && pip install "funasr>=1.2" "torchaudio>=2.13"` 然后 `pip list | grep -i "funasr\|torchaudio"`
Expected: funasr 与 torchaudio 2.13.x 出现；torch 版本不变

`backend/scripts/download_funasr_model.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""FunASR 模型预下载（modelscope，约 1GB，一次性；也可由启动预热自动完成）。

用法：cd backend && python scripts/download_funasr_model.py
"""
from modelscope import snapshot_download

if __name__ == "__main__":
    path = snapshot_download(
        "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    )
    print("模型已缓存：", path)
```

Run: `cd backend && python scripts/download_funasr_model.py`（模型较大，耐心等待完成；若网络失败重跑一次）
Expected: 输出"模型已缓存"路径；`~/.cache/modelscope/hub/damo/...` 下出现模型文件

- [ ] **Step 6: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add backend/app/services/asr_service.py backend/tests/test_asr_service.py backend/scripts/download_funasr_model.py backend/app/config.py backend/requirements.txt
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(voice): ASR 服务——FunASR 离线转写（懒加载+失败哨兵）+ 依赖钉版 + 模型预下载脚本"
```

---

### Task 2: TTS 服务（edge-tts 分句合成 + LRU 缓存）

**Files:**
- Create: `backend/app/services/tts_service.py`
- Create: `backend/tests/test_tts_service.py`
- Modify: `backend/requirements.txt`（新增 edge-tts）

**Interfaces:**
- Consumes: `app.config.settings.tts_voice`（Task 1）
- Produces（Task 4/5 依赖，逐字签名）：
  - `tts_service.split_sentences(text: str) -> list[str]`（中文标点/换行分句；>120 字按逗号再切；纯标点句丢弃）
  - `tts_service.synthesize(text: str, voice: str | None = None) -> bytes`（整段合成；网络失败重试 1 次后抛 `TTSUnavailableError`；按 (voice,text) 哈希 LRU 缓存 50 条）
  - `tts_service.synthesize_sentences(text: str, voice: str | None = None) -> Iterator[tuple[str, bytes]]`（逐句产出；单句失败跳过不中断）
  - `tts_service._communicate(text: str, voice: str) -> bytes`（测试 monkeypatch 的 seam）
  - `tts_service.TTSUnavailableError(Exception)`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_tts_service.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""TTS 服务测试：分句/缓存/重试降级（全部 mock，不真实联网）。"""
import pytest

from app.services import tts_service
from app.services.tts_service import TTSUnavailableError


@pytest.fixture(autouse=True)
def clear_cache():
    tts_service._cache.clear()
    yield
    tts_service._cache.clear()


def test_split_sentences_basic():
    assert tts_service.split_sentences("你好。欢迎！再见？") == ["你好。", "欢迎！", "再见？"]


def test_split_sentences_long_splits_by_comma():
    long_text = "学习率" + "很" * 130 + "，继续"
    parts = tts_service.split_sentences(long_text)
    assert len(parts) == 2
    assert len(parts[0]) > 120


def test_split_sentences_drops_punct_only():
    assert tts_service.split_sentences("你好。。欢迎！\n") == ["你好。", "欢迎！"]


def test_synthesize_caches(monkeypatch):
    calls = []

    def fake(text, voice):
        calls.append(text)
        return b"mp3"

    monkeypatch.setattr(tts_service, "_communicate", fake)
    assert tts_service.synthesize("你好") == b"mp3"
    assert tts_service.synthesize("你好") == b"mp3"
    assert len(calls) == 1


def test_synthesize_retry_then_raise(monkeypatch):
    def boom(text, voice):
        raise RuntimeError("网络失败")

    monkeypatch.setattr(tts_service, "_communicate", boom)
    with pytest.raises(TTSUnavailableError):
        tts_service.synthesize("你好")


def test_synthesize_sentences_skips_failed(monkeypatch):
    def flaky(text, voice):
        if text == "坏句。":
            raise RuntimeError("网络失败")
        return ("mp3-" + text).encode("utf-8")

    monkeypatch.setattr(tts_service, "_communicate", flaky)
    out = list(tts_service.synthesize_sentences("好句。坏句。也好。"))
    assert [s for s, _ in out] == ["好句。", "也好。"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_tts_service.py -v`
Expected: 全部 FAIL（`ModuleNotFoundError: app.services.tts_service`）

- [ ] **Step 3: 写最小实现**

`backend/app/services/tts_service.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""TTS 服务：edge-tts 在线合成（分句 + LRU 缓存 + 重试降级）。

edge-tts 属在线服务（端点已验证可达）：合成失败重试 1 次后抛 TTSUnavailableError，
语音链路逐句跳过、回答文字不受影响（设计文档 §6 降级口径）。
"""
import hashlib
import logging
import re
import threading
from collections import OrderedDict

from ..config import settings

logger = logging.getLogger("tts")

_SENT_SPLIT = re.compile(r"(?<=[。！？；])\s*|\n+")
_MAX_SENT = 120      # 单句超长按逗号再切
_CACHE_MAX = 50

_cache: OrderedDict[str, bytes] = OrderedDict()
_lock = threading.Lock()


class TTSUnavailableError(Exception):
    """TTS 不可用（网络/服务失败重试后仍失败）。"""


def split_sentences(text: str) -> list[str]:
    """中文标点/换行分句（保留句末标点，利于合成韵律）；超长句按逗号再切；纯标点句丢弃。"""
    raw = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    raw = [p for p in raw if any(ch not in "。！？；，" for ch in p)]
    parts = []
    for p in raw:
        if len(p) <= _MAX_SENT:
            parts.append(p)
            continue
        for sub in re.split(r"(?<=，)", p):
            sub = sub.strip()
            if sub:
                parts.append(sub)
    return parts


def _communicate(text: str, voice: str) -> bytes:
    """单次合成（测试 monkeypatch 的 seam；真实 edge_tts 仅在此懒导入）。"""
    import edge_tts
    return edge_tts.Communicate(text, voice).save_sync()


def _key(text: str, voice: str) -> str:
    return hashlib.md5(f"{voice}\x00{text}".encode("utf-8")).hexdigest()


def synthesize(text: str, voice: str | None = None) -> bytes:
    """整段合成 mp3（打字朗读路径）。缓存命中直返；失败重试 1 次后抛 TTSUnavailableError。"""
    v = voice or settings.tts_voice
    k = _key(text, v)
    with _lock:
        if k in _cache:
            return _cache[k]
    try:
        data = _communicate(text, v)
    except Exception:
        try:
            data = _communicate(text, v)
        except Exception as exc:
            raise TTSUnavailableError("语音合成服务不可用") from exc
    with _lock:
        _cache[k] = data
        _cache.move_to_end(k)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return data


def synthesize_sentences(text: str, voice: str | None = None):
    """逐句合成生成器（语音问答路径）：(句子, mp3 bytes) 逐句产出；单句失败跳过。"""
    v = voice or settings.tts_voice
    for sentence in split_sentences(text):
        try:
            yield sentence, synthesize(sentence, v)
        except TTSUnavailableError:
            logger.warning("单句合成失败，跳过：%.30s", sentence)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_tts_service.py -v`
Expected: 6 passed

- [ ] **Step 5: 钉依赖**

`backend/requirements.txt` 末尾追加：

```
edge-tts>=7.0
```

Run: `cd backend && pip install "edge-tts>=7.0"` 然后 `pip show edge-tts | head -2`
Expected: edge-tts 安装成功

- [ ] **Step 6: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add backend/app/services/tts_service.py backend/tests/test_tts_service.py backend/requirements.txt
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(voice): TTS 服务——edge-tts 分句合成 + LRU 缓存 + 重试降级"
```

---

### Task 3: kb_service 事件层重构（answer_events）

**Files:**
- Modify: `backend/app/services/kb_service.py`（ask_stream 抽出 answer_events；ask_stream 变为薄 SSE 包装）
- Test: `backend/tests/test_kb_service.py`（追加 1 个测试；既有 ask_stream 测试一行不改）

**Interfaces:**
- Consumes: 既有 `hybrid_retrieve` / `_select_hits` / `get_gateway` / `learn_profile`（同文件，不改签名）
- Produces（Task 4 依赖，逐字签名）：
  - `kb_service.answer_events(question: str, user: User, db: Session, *, vector_store=None, embedder=None, reranker=None, gateway=None) -> Iterator[tuple[str, Any]]`
  - 事件序：`("citations", list)` → `("delta", {"text": str})`* → `("done", {})`；失败 `("error", {"message": str})` 后结束（与 SSE 语义完全一致）
  - `kb_service.ask_stream(...)` 行为不变（既有 153+ 回归红线）

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_kb_service.py` 文件末尾）

```python
def test_answer_events_yields_event_tuples(tmp_path, db, monkeypatch):
    """事件层重构：answer_events 输出 (事件名, 数据) 元组（WS 语音链路直接消费）。"""
    monkeypatch.setattr(kb_service, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(kb_service, "get_vector_store", lambda: _FakeStore(tmp_path))

    class FakeGateway:
        def chat_stream(self, messages, temperature=0.7):
            yield "片段一"

    monkeypatch.setattr(kb_service, "get_gateway", lambda: FakeGateway())
    events = list(kb_service.answer_events("什么是梯度下降", _student(), db))
    names = [e for e, _ in events]
    assert names[0] == "citations"
    assert ("delta", {"text": "片段一"}) in events
    assert events[-1] == ("done", {})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_kb_service.py::test_answer_events_yields_event_tuples -v`
Expected: FAIL（`AttributeError: module 'app.services.kb_service' has no attribute 'answer_events'`）

- [ ] **Step 3: 重构实现**

`backend/app/services/kb_service.py`：将 `ask_stream` 函数体中原有的全部逻辑移入新函数 `answer_events`，把 `yield sse(event, data)` 改为 `yield (event, data)`；`ask_stream` 变为薄包装（**错误处理分支逐字保留**）：

```python
def answer_events(question: str, user: User, db: Session, *,
                  vector_store=None, embedder=None, reranker=None, gateway=None) -> Iterator[tuple[str, Any]]:
    """问答事件流（(事件名, 数据) 元组）：citations → delta* → done；失败发 error。

    ask_stream 的 SSE 字符串仅是它的薄包装；WS 语音链路（api/voice.py）直接消费本生成器。
    """
    try:
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
                "text": h.chunk.text,
                "image_path": h.chunk.meta.get("image_path"),
                "chunk_id": h.chunk.id,
            }
            for i, h in selected
        ]
        yield ("citations", citations)
        gw = gateway or get_gateway()
        for piece in gw.chat_stream(build_answer_prompt(question, hits)):
            yield ("delta", {"text": piece})
        # 工单19 画像迭代联动：学生提问命中知识点 → 记低权重事件（失败不影响问答流）
        if user.role == Role.student:
            try:
                learn_profile.record_ask_events(user, question, db)
            except Exception:
                logger.exception("画像事件记录失败（问答不受影响）")
        yield ("done", {})
    except EmbedderError as exc:
        yield ("error", {"message": str(exc)})
    except LLMError as exc:
        yield ("error", {"message": str(exc)})
    except BizError as exc:
        yield ("error", {"message": exc.message})
    except Exception:
        # 兜底：向量库检索故障/精排期异常等未预期错误也按协议发 error，不截断流（Plan C 复审 Important）
        logger.exception("知识库问答流异常")
        yield ("error", {"message": "问答服务异常，请稍后重试"})


def ask_stream(question: str, user: User, db: Session, *,
               vector_store=None, embedder=None, reranker=None, gateway=None) -> Iterator[str]:
    """流式问答（SSE 生成器）：answer_events 的 SSE 字符串包装（既有前端/测试契约不变）。"""

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    for event, data in answer_events(question, user, db,
                                     vector_store=vector_store, embedder=embedder,
                                     reranker=reranker, gateway=gateway):
        yield sse(event, data)
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `cd backend && python -m pytest tests/test_kb_service.py tests/test_kb_api.py -v`
Expected: 全部通过（含既有 ask_stream 测试一行未改）

- [ ] **Step 5: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add backend/app/services/kb_service.py backend/tests/test_kb_service.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "refactor(kb): ask_stream 抽出 answer_events 事件层（WS 语音链路复用）"
```

---

### Task 4: WS 语音问答端点 /api/voice/chat

**Files:**
- Create: `backend/app/api/voice.py`
- Create: `backend/tests/test_voice_api.py`
- Modify: `backend/app/main.py`（注册 voice 路由 + lifespan 预热 ASR）

**Interfaces:**
- Consumes: `asr_service.transcribe`/`ASRUnavailableError`（Task 1）、`tts_service.synthesize_sentences`（Task 2）、`kb_service.answer_events`（Task 3）、`core.security.decode_token`、`db.get_db`、`models.user.User`（Plan A）
- Produces（Task 6/7 前端依赖，协议逐字按设计文档 §5）：
  - WS `/api/voice/chat`，首消息 `{"type":"auth","token":JWT}` → 服务端 `{"type":"status","state":"ready"}`；无效鉴权 → `{"type":"error","message":...}` 后 close(4401)
  - `{"type":"audio","data":base64WAV}` → 事件序：`status(transcribing)` → `transcript` → `status(thinking)` → `citations` → 此后 `delta` 与 `audio{seq,data}` **交错**（句末标点落句即合成下发，边生成边播，设计文档 §3/§5）→ `done{audio_total}`；同一时刻仅一条流水线（占线回 error"正在处理中"）
  - `{"type":"cancel"}` → 停止流水线；转写阶段被打断回 `status(cancelled)`，其余阶段静默停止
  - 转写空结果 → `error("未识别到语音内容")`；ASR 未就绪 → `error("语音识别未就绪，请打字提问")`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_voice_api.py`：

```python
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


def test_ws_asr_unavailable(env, monkeypatch):
    client, token = env

    def boom(wav):
        raise ASRUnavailableError("语音识别未就绪，请打字提问")

    monkeypatch.setattr(voice, "transcribe", boom)
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        m = ws.receive_json()
        assert m["type"] == "error"
        assert "语音识别未就绪" in m["message"]


def test_ws_empty_transcript(env, monkeypatch):
    client, token = env
    monkeypatch.setattr(voice, "transcribe", lambda wav: "")
    with client.websocket_connect("/api/voice/chat") as ws:
        _auth(ws, token)
        ws.send_json({"type": "audio", "data": "eA=="})
        m = ws.receive_json()
        assert m["type"] == "error"
        assert "未识别到语音" in m["message"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_voice_api.py -v`
Expected: 全部 FAIL（`ModuleNotFoundError: app.api.voice`）

- [ ] **Step 3: 写实现**

`backend/app/api/voice.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""数字人语音接口：WS 语音问答全链路 + HTTP TTS（打字朗读，Task 5）。

WS 协议按设计文档 §5；语音流水线在独立线程消费同步生成器（answer_events/转写/TTS），
经 asyncio.Queue 转发回 WS，避免阻塞事件循环；cancel 以 threading.Event 贯穿各阶段。
"""
import asyncio
import base64
import logging
import threading

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..core.security import decode_token
from ..db import get_db
from ..models.user import User
from ..services import kb_service
from ..services.asr_service import ASRUnavailableError, transcribe
from ..services.tts_service import TTSUnavailableError, split_sentences, synthesize, synthesize_sentences

router = APIRouter()
logger = logging.getLogger("voice")


def _ends_term(text: str) -> bool:
    """缓冲区末尾是否为句末标点（该句已完整）。"""
    return text.rstrip()[-1:] in "。！？；"


def _tail(parts: list[str]) -> str:
    """句级切分后剩余未完结的尾部片段（缓冲区以句末标点结尾时为空）。"""
    return parts[-1] if parts else ""


async def _ws_user(ws: WebSocket, db: Session) -> User | None:
    """首消息 auth 鉴权：{"type":"auth","token":JWT}。失败回 error 并 close(4401)，返回 None。"""
    try:
        msg = await ws.receive_json()
    except (WebSocketDisconnect, ValueError):
        return None
    if msg.get("type") != "auth":
        await ws.send_json({"type": "error", "message": "请先发送 auth 消息"})
        await ws.close(code=4401)
        return None
    try:
        payload = decode_token(msg["token"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        user = None
    if user is None:
        await ws.send_json({"type": "error", "message": "登录已过期，请重新登录"})
        await ws.close(code=4401)
        return None
    return user


def _pipeline(wav: bytes, user: User, db: Session, cancel: threading.Event, emit) -> None:
    """语音问答流水线（独立线程）：转写 → answer_events → 句级交错 TTS；emit 线程安全入队。

    边生成边播（设计文档 §3）：delta 流中句末标点落句即合成下发；合成耗时（单句约
    0.3~1s）会短暂阻塞 LLM 流消费，聊天框文本有轻微停顿，属演示可接受换取的
    首句播报低延迟。单句合成失败静默跳过（§6 降级）。
    """
    try:
        emit({"type": "status", "state": "transcribing"})
        text = transcribe(wav)
        if cancel.is_set():
            emit({"type": "status", "state": "cancelled"})
            return
        if not text:
            emit({"type": "error", "message": "未识别到语音内容"})
            return
        emit({"type": "transcript", "text": text})
        emit({"type": "status", "state": "thinking"})
        buf = ""
        seq = 0

        def synth_sentence(sentence: str) -> None:
            nonlocal seq
            if cancel.is_set():
                return
            try:
                mp3 = synthesize(sentence)
            except TTSUnavailableError:
                return  # 单句失败静默跳过
            seq += 1
            emit({"type": "audio", "seq": seq,
                  "data": base64.b64encode(mp3).decode("ascii")})

        for event, data in kb_service.answer_events(text, user, db):
            if cancel.is_set():
                return
            if event == "citations":
                emit({"type": "citations", "items": data})
            elif event == "delta":
                emit({"type": "delta", "text": data["text"]})
                buf += data["text"]
                if any(t in buf for t in "。！？；\n"):
                    parts = split_sentences(buf)
                    complete = parts if _ends_term(buf) else parts[:-1]
                    for sentence in complete:
                        synth_sentence(sentence)
                    buf = _tail(parts) if not _ends_term(buf) else ""
            elif event == "error":
                emit({"type": "error", "message": data["message"]})
                return
        # done 后清尾：剩余未完结片段整段合成
        for sentence, mp3 in synthesize_sentences(buf):
            if cancel.is_set():
                return
            seq += 1
            emit({"type": "audio", "seq": seq,
                  "data": base64.b64encode(mp3).decode("ascii")})
        emit({"type": "done", "audio_total": seq})
    except ASRUnavailableError as exc:
        emit({"type": "error", "message": str(exc)})
    except Exception:
        logger.exception("语音问答流水线异常")
        emit({"type": "error", "message": "语音问答服务异常，请稍后重试"})


@router.websocket("/chat")
async def voice_chat(ws: WebSocket, db: Session = Depends(get_db)):
    """WS 语音问答：auth → ready；audio 触发流水线（同一时刻仅一条）；cancel 打断。"""
    await ws.accept()
    user = await _ws_user(ws, db)
    if user is None:
        return
    await ws.send_json({"type": "status", "state": "ready"})
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    cancel = threading.Event()
    drain_task: asyncio.Task | None = None

    def emit(item: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    async def drain() -> None:
        while True:
            item = await queue.get()
            if item is None:
                return
            try:
                await ws.send_json(item)
            except WebSocketDisconnect:
                return

    def run_pipeline(wav: bytes) -> None:
        try:
            _pipeline(wav, user, db, cancel, emit)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except ValueError:
                await ws.send_json({"type": "error", "message": "消息格式错误"})
                continue
            if msg.get("type") == "cancel":
                cancel.set()
            elif msg.get("type") == "audio":
                if drain_task is not None and not drain_task.done():
                    await ws.send_json({"type": "error", "message": "正在处理中，请稍候或先打断"})
                    continue
                data = msg.get("data")
                if not isinstance(data, str):
                    await ws.send_json({"type": "error", "message": "audio 消息缺少 data 字段"})
                    continue
                try:
                    wav = base64.b64decode(data, validate=True)
                except Exception:
                    await ws.send_json({"type": "error", "message": "音频数据编码无效"})
                    continue
                cancel.clear()
                drain_task = asyncio.create_task(drain())
                threading.Thread(target=run_pipeline, args=(wav,),
                                 daemon=True, name="voice-pipeline").start()
    finally:
        cancel.set()
        if drain_task is not None and not drain_task.done():
            drain_task.cancel()
```

`backend/app/main.py` 三处修改：

① 导入行追加 voice：

```python
from .api import auth, files, kb, learn, prep, voice
```

② 路由注册（learn 之后）：

```python
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
```

③ `_preheat_models()` 末尾（embedder 预热之后，顺序加载避免并发读盘）追加：

```python
    try:
        from .services.asr_service import get_asr
        ok_asr = get_asr() is not None
        logger.info("ASR 模型预热完成" if ok_asr else "ASR 模型预热跳过（语音输入将提示打字）")
    except Exception:
        logger.warning("ASR 预热异常（忽略，语音输入将降级）", exc_info=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_voice_api.py -v`
Expected: 6 passed

- [ ] **Step 5: 回归**

Run: `cd backend && python -m pytest tests/test_kb_api.py tests/test_kb_service.py -v`
Expected: 全部通过（WS 任务不触碰 kb 行为）

- [ ] **Step 6: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add backend/app/api/voice.py backend/tests/test_voice_api.py backend/app/main.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(voice): WS 语音问答端点——转写→RAG→分句TTS 全链路 + 打断/占线/降级 + ASR 启动预热"
```

---

### Task 5: HTTP TTS 端点 POST /api/voice/tts（打字朗读）

**Files:**
- Modify: `backend/app/api/voice.py`（追加 TtsIn + tts 端点）
- Test: `backend/tests/test_voice_api.py`（追加 4 个 HTTP 测试）

**Interfaces:**
- Consumes: `tts_service.synthesize`/`TTSUnavailableError`（Task 2）、`deps.get_current_user`、`core.exceptions.BizError`（Plan A）
- Produces（Task 7 依赖）：`POST /api/voice/tts` body `{"text": str}` → 200 `audio/mpeg` 字节流；空文本/超 2000 字 → 400；TTS 不可用 → 502（前端静默降级）

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_voice_api.py` 文件末尾）

```python
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

    def boom(t, v):
        raise RuntimeError("网络失败")

    monkeypatch.setattr("app.services.tts_service._communicate", boom)
    resp = client.post("/api/voice/tts", json={"text": "你好"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 502
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_voice_api.py::test_tts_requires_auth -v`
Expected: FAIL（404 Not Found）

- [ ] **Step 3: 写实现**

`backend/app/api/voice.py` 头部导入追加：

```python
from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..core.exceptions import BizError
from ..services.tts_service import TTSUnavailableError, split_sentences, synthesize, synthesize_sentences
from .deps import get_current_user
```

文件末尾追加：

```python
class TtsIn(BaseModel):
    text: str


@router.post("/tts")
def tts(data: TtsIn, user: User = Depends(get_current_user)):
    """打字朗读：整段文本合成 mp3。TTS 不可用回 502（前端 speakText 静默降级）。"""
    text = data.text.strip()
    if not text:
        raise BizError(400, "文本不能为空")
    if len(text) > 2000:
        raise BizError(400, "文本过长（最多 2000 字）")
    try:
        return Response(content=synthesize(text), media_type="audio/mpeg")
    except TTSUnavailableError as exc:
        raise BizError(502, str(exc)) from exc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_voice_api.py -v`
Expected: 10 passed（Task 4 的 6 + 本任务 4）

- [ ] **Step 5: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add backend/app/api/voice.py backend/tests/test_voice_api.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(voice): HTTP TTS 端点——打字朗读合成（鉴权/空文本/超长/降级 502）"
```

---

### Task 6: 前端基础设施（依赖 + Live2D 资源 + API/音频工具层）

> 实现者：派单前与用户确认（默认控制器直接实现）。本任务不碰 AssistantView.vue。

**Files:**
- Modify: `frontend/package.json` / `frontend/package-lock.json`（npm install 自动）
- Modify: `frontend/vite.config.ts`（proxy 加 ws: true）
- Create: `frontend/public/live2d/hiyori/`（官方样例模型文件）
- Create: `frontend/src/utils/audio.ts`
- Create: `frontend/src/api/voice.ts`
- Create: `frontend/src/components/live2d/Live2DAvatar.vue`

**Interfaces:**
- Consumes: WS 协议（Task 4）、HTTP /tts（Task 5）、auth store `useAuthStore().token`（既有）
- Produces（Task 7 依赖，逐字签名）：
  - `wavEncode(buffer: AudioBuffer) -> ArrayBuffer`、`decodeTo16k(blob: Blob) -> Promise<AudioBuffer>`、`toBase64(buf: ArrayBuffer) -> string`
  - `class PlaybackManager`：`ensureContext()`、`enqueue(blob: Blob) -> Promise<void>`、`stop()`、`get isPlaying(): boolean`、属性 `onVolume: ((v: number) => void) | null`、`onEnd: (() => void) | null`
  - `speakText(text: string) -> Promise<Blob | null>`（502/网络失败返回 null）
  - `class VoiceClient`：`connect(handlers: VoiceHandlers)`、`sendAudio(wavBase64: string)`、`cancel()`、`close()`、`get isOpen(): boolean`；`VoiceHandlers = { onEvent: (e: VoiceEvent) => void; onClose: (reason: string) => void }`
  - `Live2DAvatar` 组件（expose `setMouth(v: number)`）

- [ ] **Step 1: 安装依赖**

```bash
cd frontend
npm install pixi.js@^7.4.2 pixi-live2d-display@^0.4.0
```

Expected: 安装成功，package.json dependencies 出现 `"pixi.js": "^7.4.2"` 与 `"pixi-live2d-display": "^0.4.0"`（**禁 pixi.js v8**）

- [ ] **Step 2: vite proxy 开 WS**

`frontend/vite.config.ts` 的 server 段改为：

```ts
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true } }
  }
```

- [ ] **Step 3: 下载 Live2D 官方样例模型（Hiyori）**

```bash
mkdir -p frontend/public/live2d
curl -L -o /tmp/hiyori.zip https://cubism.live2d.com/sample-data/hiyori/hiyori.zip
cd frontend/public/live2d && python -c "import zipfile; zipfile.ZipFile('/tmp/hiyori.zip').extractall('.')"
ls hiyori/
```

Expected: `hiyori/` 下含 `hiyori.model3.json`、`hiyori.moc3`、`textures/`、`motions/`、`expressions/`（若官方直链 404：改从 https://www.live2d.com/download/sample-data/ 手动下载 Hiyori zip 后解压到同路径，并告知控制器）

- [ ] **Step 4: 音频工具层**

`frontend/src/utils/audio.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
// 音频工具：WAV 编码（16k 单声道 PCM，供后端 FunASR）+ 播放器（音量驱动口型）

/** AudioBuffer → 16 位 PCM WAV（单声道，采样率不变；调用方先经 decodeTo16k 重采样）。 */
export function wavEncode(buffer: AudioBuffer): ArrayBuffer {
  const numCh = 1
  const rate = buffer.sampleRate
  const data = buffer.getChannelData(0)
  const blockAlign = numCh * 2
  const buf = new ArrayBuffer(44 + data.length * blockAlign)
  const view = new DataView(buf)
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + data.length * blockAlign, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, numCh, true)
  view.setUint32(24, rate, true)
  view.setUint32(28, rate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, data.length * blockAlign, true)
  let off = 44
  for (let i = 0; i < data.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, data[i]))
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return buf
}

/** webm/opus Blob → 16k 单声道 AudioBuffer（decodeAudioData + OfflineAudioContext 重采样，零后端 ffmpeg）。 */
export async function decodeTo16k(blob: Blob): Promise<AudioBuffer> {
  const arrayBuf = await blob.arrayBuffer()
  const ctx = new AudioContext()
  try {
    const decoded = await ctx.decodeAudioData(arrayBuf)
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000)
    const src = offline.createBufferSource()
    src.buffer = decoded
    src.connect(offline.destination)
    src.start()
    return await offline.startRendering()
  } finally {
    void ctx.close()
  }
}

/** ArrayBuffer → base64（分块拼接避免大数组展开爆栈）。 */
export function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  const step = 0x8000
  for (let i = 0; i < bytes.length; i += step) {
    bin += String.fromCharCode(...bytes.subarray(i, i + step))
  }
  return btoa(bin)
}

/** mp3 顺序播放器：AnalyserNode 取音量回调（驱动 Live2D 口型）；stop() 立即静音。 */
export class PlaybackManager {
  onVolume: ((v: number) => void) | null = null
  onEnd: (() => void) | null = null

  private ctx: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private queue: AudioBuffer[] = []
  private playing = false
  private stopped = false

  /** 用户手势后调用一次（按住说话/发送/开关切换均满足 Chrome 自动播放策略）。 */
  ensureContext() {
    if (!this.ctx) {
      this.ctx = new AudioContext()
      this.analyser = this.ctx.createAnalyser()
      this.analyser.fftSize = 512
      this.analyser.connect(this.ctx.destination)
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume()
  }

  /** 入队一段 mp3 blob（解码后顺序播放；stop() 清空）。 */
  async enqueue(blob: Blob) {
    this.ensureContext()
    const buf = await this.ctx!.decodeAudioData(await blob.arrayBuffer())
    this.queue.push(buf)
    if (!this.playing) void this.playLoop()
  }

  get isPlaying() { return this.playing }

  stop() {
    this.stopped = true
    this.queue = []
    void this.ctx?.close()
    this.ctx = null
    this.analyser = null
    this.playing = false
    this.onVolume?.(0)
  }

  private async playLoop() {
    this.playing = true
    this.stopped = false
    const data = new Uint8Array(this.analyser!.fftSize)
    const tick = () => {
      if (!this.stopped && this.analyser) {
        this.analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128
          sum += v * v
        }
        this.onVolume?.(Math.min(1, Math.sqrt(sum / data.length) * 4))
        requestAnimationFrame(tick)
      } else {
        this.onVolume?.(0)
      }
    }
    requestAnimationFrame(tick)
    while (this.queue.length && !this.stopped) {
      const buf = this.queue.shift()!
      await this.playBuffer(buf)
    }
    this.playing = false
    if (!this.stopped) this.onEnd?.()
  }

  private playBuffer(buf: AudioBuffer) {
    return new Promise<void>((resolve) => {
      const ctx = this.ctx!
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(this.analyser!)
      src.onended = () => resolve()
      src.start()
    })
  }
}
```

- [ ] **Step 5: 语音 API 层**

`frontend/src/api/voice.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
import http from './http'
import { useAuthStore } from '@/stores/auth'
import type { KbCitation } from './kb'

export type VoiceEvent =
  | { type: 'status'; state: 'ready' | 'transcribing' | 'thinking' | 'cancelled' }
  | { type: 'transcript'; text: string }
  | { type: 'citations'; items: KbCitation[] }
  | { type: 'delta'; text: string }
  | { type: 'audio'; seq: number; data: string }
  | { type: 'done'; audio_total: number }
  | { type: 'error'; message: string }

export interface VoiceHandlers {
  onEvent: (e: VoiceEvent) => void
  onClose: (reason: string) => void
}

/** 打字朗读：整段文本合成 mp3；TTS 不可用（502/网络失败）返回 null（前端静默降级）。 */
export async function speakText(text: string): Promise<Blob | null> {
  try {
    const resp = await http.post('/voice/tts', { text }, { responseType: 'blob' })
    return resp as unknown as Blob
  } catch {
    return null
  }
}

/** WS 语音客户端：首消息 auth 鉴权；断线自动重连（最多 3 次）。 */
export class VoiceClient {
  private ws: WebSocket | null = null
  private retries = 0
  private closedByUser = false
  private handlers: VoiceHandlers | null = null

  connect(handlers: VoiceHandlers) {
    this.handlers = handlers
    this.closedByUser = false
    this.open()
  }

  private open() {
    const auth = useAuthStore()
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${proto}://${window.location.host}/api/voice/chat`)
    this.ws.onopen = () => {
      this.retries = 0
      this.send({ type: 'auth', token: auth.token })
    }
    this.ws.onmessage = (ev) => {
      try {
        this.handlers?.onEvent(JSON.parse(ev.data))
      } catch {
        // 脏帧忽略
      }
    }
    this.ws.onclose = () => {
      if (this.closedByUser) return
      this.retries += 1
      if (this.retries > 3) {
        this.handlers?.onClose('语音连接断开，请刷新页面重试')
        return
      }
      this.handlers?.onClose('语音连接已断开，正在重连…')
      setTimeout(() => this.open(), 2000)
    }
  }

  get isOpen() { return this.ws?.readyState === WebSocket.OPEN }

  sendAudio(wavBase64: string) { this.send({ type: 'audio', data: wavBase64 }) }

  cancel() { this.send({ type: 'cancel' }) }

  close() {
    this.closedByUser = true
    this.ws?.close()
  }

  private send(obj: unknown) {
    if (this.isOpen) this.ws!.send(JSON.stringify(obj))
  }
}
```

- [ ] **Step 6: Live2D 组件**

`frontend/src/components/live2d/Live2DAvatar.vue`：

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展) -->
<template>
  <div ref="canvasHost" class="avatar-canvas" />
</template>

<script setup lang="ts">
// Live2D 渲染器封装：加载官方样例模型 + 音量驱动口型 + 呼吸/待机（Pixi 与 Vue 响应式隔离）
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as PIXI from 'pixi.js'
import { Live2DModel } from 'pixi-live2d-display'

const canvasHost = ref<HTMLElement>()
let app: PIXI.Application | null = null
let model: Live2DModel | null = null
let mouthParam = ''
let breathParam = ''
let lastMouth = 0
let rafId = 0

onMounted(async () => {
  app = new PIXI.Application({ resizeTo: canvasHost.value, backgroundAlpha: 0 })
  canvasHost.value!.appendChild(app.view as unknown as Node)
  try {
    model = await Live2DModel.from('/live2d/hiyori/hiyori.model3.json')
    // 适配面板：底部对齐、宽度自适应
    const scale = Math.min(app.screen.width / model.width, 1.2)
    model.scale.set(scale)
    model.x = (app.screen.width - model.width * scale) / 2
    model.y = app.screen.height - model.height * scale
    app.stage.addChild(model)
    mouthParam = findParam(model, /MouthOpen/i, 'ParamMouthOpenY')
    breathParam = findParam(model, /Breath/i, 'ParamBreath')
    try { model.motion('idle') } catch { /* 无 idle motion 时走手动呼吸 */ }
    rafId = requestAnimationFrame(tick)
  } catch (e) {
    console.error('Live2D 加载失败', e)
  }
})

function findParam(m: Live2DModel, re: RegExp, fallback: string): string {
  const names: string[] = (m as any).internalModel?.coreModel?.parameters?.ids ?? []
  return names.find((n) => re.test(n)) ?? fallback
}

function setParam(core: any, id: string, v: number) {
  try {
    if (typeof core.setParamFloat === 'function') core.setParamFloat(id, v)
    else if (typeof core.setParameterValueById === 'function') core.setParameterValueById(id, v)
  } catch {
    // 参数不存在时忽略
  }
}

function tick() {
  if (model && mouthParam) {
    const core = (model as any).internalModel?.coreModel
    setParam(core, mouthParam, lastMouth)
    if (breathParam) {
      const t = performance.now() / 1000
      setParam(core, breathParam, 0.5 + 0.5 * Math.sin(t * 0.9))  // 呼吸 0~1
    }
  }
  rafId = requestAnimationFrame(tick)
}

/** 音量 0~1 直驱口型（PlaybackManager.onVolume 每帧回调）。 */
function setMouth(v: number) {
  lastMouth = Math.max(0, Math.min(1, v))
}

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  model?.destroy()
  app?.destroy(true)
})

defineExpose({ setMouth })
</script>

<style scoped>
.avatar-canvas { width: 100%; height: 100%; }
</style>
```

- [ ] **Step 7: 验证**

Run: `cd frontend && npm run build` 然后 `npx tsc --noEmit`
Expected: build 成功、tsc 0 错误

- [ ] **Step 8: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/public/live2d/hiyori frontend/src/utils/audio.ts frontend/src/api/voice.ts frontend/src/components/live2d/Live2DAvatar.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(voice): 前端基础设施——pixi/live2d 依赖 + Hiyori 样例模型 + 音频工具 + WS 客户端 + Live2D 组件"
```

---

### Task 7: 智能助教页数字人面板集成

> 实现者：派单前与用户确认（默认控制器直接实现）。**不碰 LoginView.vue 与 HomeView.vue**；若用户正在并行编辑 AssistantView.vue，先与控制器同步。

**Files:**
- Modify: `frontend/src/views/assistant/AssistantView.vue`

**Interfaces:**
- Consumes: Task 6 全部产物（`Live2DAvatar`/`PlaybackManager`/`wavEncode`/`decodeTo16k`/`toBase64`/`VoiceClient`/`speakText`/`VoiceEvent`）
- Produces: 数字人互动面板（按住说话/打断/静音/状态）+ 语音问答进聊天框 + 打字朗读钩子

**验收口径（彩排清单，逐字）：**
1. 打字提问 → 聊天框照常渲染 + 数字人口型朗读；静音开关生效
2. 按住说话语音提问 → 转写进聊天框 → 回答流式渲染 + 分句朗读
3. 播报中点击打断 → 立即停声，可继续下一次提问
4. TTS 不可用（断网）→ 回答文字正常、朗读静默降级不报错
5. 刷新页面 → WS 重连、待机动画正常

- [ ] **Step 1: 模板改造（三处）**

① 布局三栏（原 kb 8 / chat 16 → kb 7 / chat 12 / 数字人 5）：

```vue
  <el-row :gutter="16" class="assistant-row">
    <!-- 知识库 -->
    <el-col :span="7">
```

```vue
    <!-- 对话区 -->
    <el-col :span="12">
```

② 对话区 `</el-col>` 之后、`</el-row>` 之前插入数字人面板：

```vue
    <!-- 数字人互动 -->
    <el-col :span="5">
      <el-card class="avatar-card">
        <template #header>
          <div class="card-head">
            <span><el-icon class="head-icon"><Microphone /></el-icon>数字人互动</span>
            <el-switch v-model="muted" size="small" inline-prompt active-text="静音" inactive-text="朗读" @change="onMute" />
          </div>
        </template>
        <div class="avatar-stage">
          <Live2DAvatar ref="avatarRef" />
        </div>
        <div class="avatar-state">{{ voiceStateText }}</div>
        <el-button class="talk-btn" type="primary" size="large" :loading="voiceState === 'transcribing' || voiceState === 'thinking'"
          :disabled="!voiceReady || answering" @pointerdown="startTalk" @pointerup="stopTalk"
          @pointerleave="stopTalk" @pointercancel="stopTalk">
          <el-icon class="btn-ico"><Microphone /></el-icon>{{ talking ? '松开结束' : '按住说话' }}
        </el-button>
        <el-button v-if="voiceState === 'playing' || voiceState === 'transcribing' || voiceState === 'thinking'"
          class="stop-btn" type="danger" plain @click="interrupt">
          <el-icon class="btn-ico"><VideoPause /></el-icon>打断
        </el-button>
        <el-alert type="info" :closable="false" class="avatar-alert"
          title="需允许麦克风权限；语音识别本地完成，录音不出本机" />
      </el-card>
    </el-col>
  </el-row>
```

③ 输入框禁用条件加语音忙时（打字与语音不并发）：

```vue
          <el-input v-model="question" placeholder="基于知识库提问，如：梯度下降的学习率怎么选？"
            @keyup.enter="onAsk" :disabled="answering || voiceBusy" size="large" class="chat-input-box" />
          <el-button type="primary" size="large" :loading="answering" :disabled="voiceBusy" @click="onAsk" class="send-btn">
```

- [ ] **Step 2: script 改造**

① imports 追加：

```ts
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound, Collection, DataAnalysis, Delete, Document, MagicStick,
  Microphone, Notebook, Picture, Promotion, Tickets, UploadFilled, VideoPause,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import {
  askStream, deleteKbDocument, listKbDocuments, loadChunkImage,
  uploadKbDocument, type KbCitation, type KbDocument,
} from '@/api/kb'
import { speakText, VoiceClient, type VoiceEvent } from '@/api/voice'
import { decodeTo16k, PlaybackManager, toBase64, wavEncode } from '@/utils/audio'
import Live2DAvatar from '@/components/live2d/Live2DAvatar.vue'
```

② 状态与常量（`const images = ...` 行之后追加）：

```ts
// ---------- 数字人 ----------
const muted = ref(false)
const voiceReady = ref(false)
const talking = ref(false)
const voiceState = ref<'idle' | 'recording' | 'transcribing' | 'thinking' | 'playing'>('idle')
const avatarRef = ref<InstanceType<typeof Live2DAvatar>>()
const player = new PlaybackManager()
const voice = new VoiceClient()
let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
let stream: MediaStream | null = null
let talkTimer: number | undefined
let voiceMsg: Msg | null = null   // 语音模式的 assistant 消息（复用聊天框渲染）

const voiceBusy = computed(() => ['recording', 'transcribing', 'thinking'].includes(voiceState.value))
const voiceStateText = computed(() => ({
  idle: '待机中', recording: '正在聆听…', transcribing: '识别中…', thinking: '思考中…', playing: '播报中',
} as const)[voiceState.value])
```

③ 事件处理与录制（`onAsk` 函数之后追加，`onMounted` 之前）：

```ts
function onVoiceEvent(e: VoiceEvent) {
  if (e.type === 'status') {
    if (e.state === 'ready' || e.state === 'cancelled') {
      voiceReady.value = true
      if (e.state !== 'ready') voiceState.value = 'idle'
    } else if (e.state === 'transcribing') voiceState.value = 'transcribing'
    else if (e.state === 'thinking') voiceState.value = 'thinking'
  } else if (e.type === 'transcript') {
    messages.value.push({ role: 'user', text: e.text, at: new Date().toISOString() })
    voiceMsg = { role: 'assistant', text: '', at: new Date().toISOString() }
    messages.value.push(voiceMsg)
    scrollBottom()
  } else if (e.type === 'citations') {
    if (voiceMsg) {
      voiceMsg.citations = e.items
      e.items.filter((c) => c.kind === 'image').forEach((c) => { void loadImg(c.chunk_id) })
      scrollBottom()
    }
  } else if (e.type === 'delta') {
    if (voiceMsg) { voiceMsg.text += e.text; scrollBottom() }
  } else if (e.type === 'audio') {
    const bytes = atob(e.data)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    void player.enqueue(new Blob([arr], { type: 'audio/mpeg' }))
  } else if (e.type === 'done') {
    if (voiceMsg && !voiceMsg.text) voiceMsg.text = '（无内容）'
    voiceMsg = null
    if (e.audio_total > 0) voiceState.value = 'playing'
    else voiceState.value = 'idle'
  } else if (e.type === 'error') {
    voiceMsg = null
    voiceState.value = 'idle'
    ElMessage.error(e.message)
  }
}

function onVoiceClose(reason: string) {
  voiceReady.value = false
  if (reason !== 'closed') ElMessage.warning(reason)
}

async function startTalk() {
  if (!voiceReady.value || answering.value || talking.value) return
  if (player.isPlaying) interrupt()
  try {
    if (!stream) stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
    return
  }
  chunks = []
  recorder = new MediaRecorder(stream)
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
  recorder.onstop = onRecordEnd
  recorder.start()
  talking.value = true
  voiceState.value = 'recording'
  talkTimer = window.setTimeout(stopTalk, 60000)  // 最长 60s 自动松开
}

function stopTalk() {
  if (!talking.value) return
  talking.value = false
  if (talkTimer) { clearTimeout(talkTimer); talkTimer = undefined }
  try { recorder?.stop() } catch { /* 已停止 */ }
}

async function onRecordEnd() {
  const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
  if (blob.size < 1000) { voiceState.value = 'idle'; return }  // 过短视为误触
  try {
    const buf16k = await decodeTo16k(blob)
    voice.sendAudio(toBase64(wavEncode(buf16k)))
  } catch {
    voiceState.value = 'idle'
    ElMessage.error('录音处理失败，请重试')
  }
}

function interrupt() {
  player.stop()
  voice.cancel()
  voiceState.value = 'idle'
}

function onMute(v: string | number | boolean) {
  if (v) interrupt()  // 静音即打断当前播报
}
```

④ `onAsk` 尾部追加打字朗读钩子（`finally { answering.value = false }` 之后）：

```ts
  if (!muted.value && msg.text && !msg.text.startsWith('生成失败') && msg.text !== '（无内容）') {
    if (player.isPlaying) player.stop()
    const blob = await speakText(msg.text.slice(0, 2000))
    if (blob) {
      voiceState.value = 'playing'
      await player.enqueue(blob)
    }
  }
```

⑤ 生命周期接线（替换原 `onMounted(loadDocs)` 一行）：

```ts
onMounted(() => {
  player.onVolume = (v) => avatarRef.value?.setMouth(v)
  player.onEnd = () => { voiceState.value = 'idle' }
  voice.connect({ onEvent: onVoiceEvent, onClose: onVoiceClose })
  void loadDocs()
})

onBeforeUnmount(() => {
  voice.close()
  player.stop()
  stream?.getTracks().forEach((t) => t.stop())
})
```

- [ ] **Step 3: 样式追加**（`</style>` 之前）

```css
/* ---------- 数字人 ---------- */
.avatar-card { height: 100%; display: flex; flex-direction: column; }
.avatar-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.avatar-stage { flex: 1; min-height: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.avatar-state { margin-top: 10px; text-align: center; font-size: 12.5px; color: var(--text-3); }
.talk-btn { width: 100%; margin-top: 10px; }
.stop-btn { width: 100%; margin-top: 8px; }
.avatar-alert { margin-top: 10px; }
.avatar-alert :deep(.el-alert__title) { font-size: 12px; }
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build` 然后 `npx tsc --noEmit`
Expected: build 成功、tsc 0 错误

- [ ] **Step 5: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add frontend/src/views/assistant/AssistantView.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(voice): 助教页数字人面板——按住说话/打断/静音 + 语音问答进聊天框 + 打字朗读"
```

---

### Task 8: 文档与全量回归

**Files:**
- Modify: `README.md`
- Modify: `docs/工单18-智能助教-测试用例与结果.md`

**Interfaces:**
- Consumes: 全链路（Task 1~7）
- Produces: 文档口径（数字人使用说明 + Live2D 版权声明 + 测试用例与彩排清单）

- [ ] **Step 1: README 更新**

① 工单对照表工单18 行改为：

```markdown
| 18 | 智能助教（多模态RAG） | ✅ Plan C + 数字人交互（Plan E：语音问答/朗读/Live2D） |
```

② 目录结构段之后新增"数字人互动"小节：

```markdown
## 数字人互动（智能助教内嵌）

- 语音问答：助教页按住说话 → FunASR 本地转写（paraformer-zh，录音不出本机）→ 知识库 RAG → edge-tts 分句朗读，Live2D 形象音量驱动口型；播报中可一键打断
- 打字朗读：文字问答的回答默认朗读，右上角开关可静音
- 依赖：`pip install -r requirements.txt`（funasr/torchaudio/edge-tts）；FunASR 模型首次使用自动下载（约 1GB，modelscope），或先跑 `python scripts/download_funasr_model.py` 预热；edge-tts 需联网（失败自动降级为纯文字）
- 浏览器：建议 Chrome/Edge；首次按住说话时授权麦克风
- 形象版权：Hiyori 为 Live2D 官方样例模型（Live2D Free Material License，可商用演示，保留本声明）
```

- [ ] **Step 2: 测试文档追加用例**

`docs/工单18-智能助教-测试用例与结果.md` 末尾追加"数字人交互（Plan E）"节：

```markdown
## 数字人交互（Plan E，2026-09-19）

| 用例 | 步骤 | 预期 | 结果 |
|---|---|---|---|
| 后端 | pytest：tests/test_asr_service.py / test_tts_service.py / test_voice_api.py（16 用例，全部 mock） | 全过 | 待回填 |
| 30+1 | 打字提问 | 聊天框照常 + 数字人口型朗读；静音开关生效 | 待彩排 |
| 30+2 | 按住说话语音提问 | 转写进聊天框 → 回答流式 + 分句朗读 | 待彩排 |
| 30+3 | 播报中点击打断 | 立即停声，可继续下一次提问 | 待彩排 |
| 30+4 | TTS 不可用（断网） | 回答文字正常、朗读静默降级不报错 | 待彩排 |
| 30+5 | 刷新页面 | WS 重连、待机动画正常 | 待彩排 |
```

- [ ] **Step 3: 全量回归**

Run: `cd backend && python -m pytest`
Expected: 基线 153 passed, 2 deselected + 新增 16（4 asr + 6 tts + 1 kb + 10 voice - 4 kb 既有重复 = 16）= **169 passed, 2 deselected**（数字以实跑为准，不得低于基线 + 新增数）

Run: `cd frontend && npm run build && npx tsc --noEmit`
Expected: build 成功、tsc 0 错误

- [ ] **Step 4: 提交**

```bash
cd /c/Users/38668/Desktop/项目/数字人/edu-agent-platform
git add README.md "docs/工单18-智能助教-测试用例与结果.md"
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "docs(voice): 数字人使用说明 + Live2D 版权声明 + 测试用例与彩排清单"
```

---

## 计划完成后的控制器收尾（不在任务内）

1. 终审：逐任务评审 + Minor 台账裁定（.superpowers/sdd/progress.md）
2. 彩排清单交付用户浏览器执行（含 Plan D 用例30 未回填项），结果回填测试文档
3. dev → master 合并（finishing-a-development-branch），全量回归后删 dev
4. 记忆更新：[[digital-human-realtime-plan]] 状态、[[edu-agent-platform-status]] 进度
