import pytest

from aliyun_oss_rag.config import get_settings
from aliyun_oss_rag.embeddings import EmbeddingClient, embeddings_endpoint
from aliyun_oss_rag.llm import LLMClient, chat_completions_endpoint


def test_settings_use_required_llm_env(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("MODEL", "mimo-v2.5-pro")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embedding.example.com/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-model")

    settings = get_settings()

    assert settings.base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert settings.api_key == "test-key"
    assert settings.model == "mimo-v2.5-pro"
    assert settings.embedding_configured
    assert settings.embedding_model == "embedding-model"


def test_llm_client_requires_three_env_values():
    with pytest.raises(ValueError, match="BASE_URL, API_KEY, MODEL"):
        LLMClient(api_key="", model="", base_url="")


def test_chat_completion_endpoint_normalization():
    assert chat_completions_endpoint("https://example.com") == "https://example.com/v1/chat/completions"
    assert chat_completions_endpoint("https://example.com/v1") == "https://example.com/v1/chat/completions"
    assert chat_completions_endpoint("https://example.com/v1/chat/completions") == "https://example.com/v1/chat/completions"


def test_embedding_client_requires_three_env_values():
    with pytest.raises(ValueError, match="EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL"):
        EmbeddingClient(api_key="", model="", base_url="")


def test_embedding_endpoint_normalization():
    assert embeddings_endpoint("https://example.com") == "https://example.com/v1/embeddings"
    assert embeddings_endpoint("https://example.com/v1") == "https://example.com/v1/embeddings"
    assert embeddings_endpoint("https://example.com/v1/embeddings") == "https://example.com/v1/embeddings"
