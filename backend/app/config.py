# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""全局配置：从 backend/.env 读取，未配置项使用默认值。

密钥安全：**仓库里不允许存在可用的默认 JWT 密钥**。历史版本把开发密钥硬编码在此处，
而 backend/.env 是 gitignore 的——任何一次没配 .env 的启动都会用那串"写在仓库里、
人人都知道"的密钥签发 token，等于任何人可伪造任意 user_id 的合法 token。

现在的处理：
  - .env 显式配置 SECRET_KEY  → 直接用；
  - 未配置且 APP_ENV=dev      → 自动生成随机密钥并持久化到 backend/.secret_key
                                （已 gitignore），保证重启后 token 不失效；
  - 未配置且 APP_ENV=prod     → 直接拒绝启动。
"""
import logging
import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config")

# 历史硬编码的开发密钥。保留此常量**仅用于识别"未配置"状态**，绝不作为可用密钥。
_LEGACY_INSECURE_SECRET = "edu-agent-dev-secret-key-9f8e7d6c5b4a3210-change-me"
# 锚定到 backend/（app/config.py 的上两级），不随 CWD 漂移：否则从仓库根启动时会生成到
# 未被 gitignore 覆盖的位置，把本地密钥提交上去。
_SECRET_FILE = Path(__file__).resolve().parent.parent / ".secret_key"
_PROD_ENVS = {"prod", "production"}
_GEN_CMD = "python -c \"import secrets;print(secrets.token_urlsafe(48))\""  # noqa: E501


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "edu-agent-platform"
    app_env: str = "dev"          # dev | prod；prod 下强制要求显式配置 SECRET_KEY
    secret_key: str = ""          # 留空表示未配置，由 _resolve_secret_key() 补齐
    access_token_expire_minutes: int = 60 * 24
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 存储
    db_url: str = "sqlite:///./data/app.db"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 50
    # 向量与模型
    embedding_model: str = "BAAI/bge-m3"
    vector_backend: str = "milvus"  # milvus | faiss
    milvus_uri: str = "./data/milvus.db"
    # 数字人语音
    asr_model: str = "paraformer-zh"        # 批量离线转写（按住说话 / 流式降级兜底）
    asr_stream_model: str = "paraformer-zh-streaming"   # 流式增量转写（自然轮次对话）
    vad_model: str = "fsmn-vad"             # 服务端端点检测（自动断句）
    voice_stream_enabled: bool = True       # 流式语音会话总开关（模型不可用时自动关闭）
    tts_voice: str = "zh-CN-XiaoyiNeural"   # 晓伊·元气少女音：匹配朵娅的二次元形象
    tts_pitch: str = "+15Hz"                # 音调调高更萌（edge-tts 频率偏移）


def _resolve_secret_key(cfg: Settings) -> None:
    """确保 secret_key 可用：显式配置优先，否则 dev 随机生成落盘 / prod 拒绝启动。

    落盘而非"每次进程启动随机生成"是有意为之：随机密钥若只存在于内存，每次重启都会
    让所有人已签发的 token 失效（演示时前端一直掉登录）。持久化随机密钥同时满足
    "不可预测"与"重启不失效"。
    """
    if cfg.secret_key and cfg.secret_key != _LEGACY_INSECURE_SECRET:
        return

    if cfg.app_env.strip().lower() in _PROD_ENVS:
        raise RuntimeError(
            f"APP_ENV={cfg.app_env} 但未配置 SECRET_KEY：拒绝用可预测的密钥签发 JWT。"
            f"请在 backend/.env 中设置 SECRET_KEY=<随机串>（生成：{_GEN_CMD}）。"
        )

    if _SECRET_FILE.exists():
        existing = _SECRET_FILE.read_text(encoding="utf-8").strip()
        if existing:
            cfg.secret_key = existing
            return

    key = secrets.token_urlsafe(48)
    _SECRET_FILE.write_text(key, encoding="utf-8")
    try:
        os.chmod(_SECRET_FILE, 0o600)   # Windows 上权限位语义有限，尽力而为
    except OSError:
        pass
    cfg.secret_key = key
    logger.warning(
        "未在 backend/.env 配置 SECRET_KEY，已生成随机密钥并保存到 %s（已 gitignore）。"
        "若要固定密钥（如多机部署需互相认 token），请在 .env 中显式设置 SECRET_KEY。",
        _SECRET_FILE.resolve(),
    )


settings = Settings()
_resolve_secret_key(settings)
