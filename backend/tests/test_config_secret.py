# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""配置安全测试：仓库里不允许存在可用的默认 JWT 密钥。

背景：旧实现把开发密钥硬编码在 config.py，而 backend/.env 是 gitignore 的——
任何一次没配 .env 的启动都用那串"仓库里公开可见"的密钥签发 token，
知道这串即可伪造任意 user_id 的合法 token。
"""
import pytest

from app import config


@pytest.fixture
def secret_file(tmp_path, monkeypatch):
    """把密钥落盘位置指向临时目录，避免污染真实的 backend/.secret_key。"""
    p = tmp_path / ".secret_key"
    monkeypatch.setattr(config, "_SECRET_FILE", p)
    return p


def test_dev_generates_random_secret_when_unset(secret_file):
    cfg = config.Settings(secret_key="", app_env="dev")
    config._resolve_secret_key(cfg)
    assert cfg.secret_key
    assert cfg.secret_key != config._LEGACY_INSECURE_SECRET
    assert len(cfg.secret_key) >= 32
    assert secret_file.read_text(encoding="utf-8").strip() == cfg.secret_key


def test_legacy_default_is_treated_as_unconfigured(secret_file):
    """即便有人把历史默认密钥填回 .env，也不得被当作有效配置。"""
    cfg = config.Settings(secret_key=config._LEGACY_INSECURE_SECRET, app_env="dev")
    config._resolve_secret_key(cfg)
    assert cfg.secret_key != config._LEGACY_INSECURE_SECRET


def test_generated_secret_is_persisted_across_restarts(secret_file):
    """随机密钥落盘：重启后复用同一密钥，已签发 token 不失效。"""
    first = config.Settings(secret_key="", app_env="dev")
    config._resolve_secret_key(first)
    second = config.Settings(secret_key="", app_env="dev")
    config._resolve_secret_key(second)
    assert first.secret_key == second.secret_key


def test_existing_secret_file_is_reused(secret_file):
    secret_file.write_text("persisted-key-value", encoding="utf-8")
    cfg = config.Settings(secret_key="", app_env="dev")
    config._resolve_secret_key(cfg)
    assert cfg.secret_key == "persisted-key-value"


def test_explicit_secret_is_kept_as_is(secret_file):
    cfg = config.Settings(secret_key="explicit-key-not-rotated", app_env="dev")
    config._resolve_secret_key(cfg)
    assert cfg.secret_key == "explicit-key-not-rotated"
    assert not secret_file.exists()          # 显式配置不落盘


@pytest.mark.parametrize("app_env", ["prod", "production", "PROD"])
def test_prod_without_secret_refuses_to_start(secret_file, app_env):
    cfg = config.Settings(secret_key="", app_env=app_env)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config._resolve_secret_key(cfg)
    assert not secret_file.exists()          # 拒绝启动时不得留下半成品文件


def test_prod_with_explicit_secret_starts(secret_file):
    cfg = config.Settings(secret_key="k" * 40, app_env="prod")
    config._resolve_secret_key(cfg)          # 不抛异常即通过
    assert cfg.secret_key == "k" * 40


def test_default_secret_field_is_empty():
    """字段默认值必须是空串（"未配置"信号），不得是任何可用密钥。"""
    assert config.Settings.model_fields["secret_key"].default == ""
