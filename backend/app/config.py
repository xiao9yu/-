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
    asr_model: str = "paraformer-zh"
    tts_voice: str = "zh-CN-XiaoyiNeural"   # 晓伊·少女音：匹配朵娅的二次元形象


settings = Settings()
