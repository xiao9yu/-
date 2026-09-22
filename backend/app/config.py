# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""全局配置：从 backend/.env 读取，未配置项使用默认值。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "edu-agent-platform"
    secret_key: str = "edu-agent-dev-secret-key-9f8e7d6c5b4a3210-change-me"
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


settings = Settings()
