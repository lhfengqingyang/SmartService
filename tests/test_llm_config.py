import pytest

from app.config import get_llm_settings


def test_qianwen_provider_uses_own_key_without_changing_embedding(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qianwen")
    monkeypatch.setenv("QIANWEN_API_KEY", "qianwen-test-key")
    monkeypatch.delenv("QIANWEN_BASE_URL", raising=False)
    monkeypatch.delenv("QIANWEN_MODEL", raising=False)

    settings = get_llm_settings()

    assert settings.api_key == "qianwen-test-key"
    assert settings.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert settings.model == "qwen3.7-flash"


def test_zhipu_provider_still_supported(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "zhipu")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-test-key")
    monkeypatch.delenv("ZHIPU_BASE_URL", raising=False)
    monkeypatch.delenv("ZHIPU_MODEL", raising=False)

    settings = get_llm_settings()

    assert settings.api_key == "zhipu-test-key"
    assert settings.model == "glm-4.7-flash"


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        get_llm_settings()
