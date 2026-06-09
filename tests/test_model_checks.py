from aliyun_oss_rag.config import Settings
from aliyun_oss_rag.model_checks import check_embedding_model, check_llm_model, check_models


class FakeLLMClient:
    model = "chat-test"
    endpoint = "https://chat.example.com/v1/chat/completions"

    def generate(self, prompt: str) -> str:
        assert "连通性测试" in prompt
        return "OK"


class FakeEmbeddingClient:
    model = "embedding-test"
    endpoint = "https://embedding.example.com/v1/embeddings"

    def embed(self, texts):
        assert texts == ["OSS RAG embedding connectivity test"]
        return [[0.1, 0.2, 0.3]]


def configured_settings() -> Settings:
    return Settings(
        base_url="https://chat.example.com/v1",
        api_key="chat-key",
        model="chat-test",
        embedding_base_url="https://embedding.example.com/v1",
        embedding_api_key="embedding-key",
        embedding_model="embedding-test",
    )


def test_check_models_reports_available_clients(monkeypatch):
    monkeypatch.setattr("aliyun_oss_rag.model_checks.get_llm", lambda settings: FakeLLMClient())
    monkeypatch.setattr("aliyun_oss_rag.model_checks.get_embedding_client", lambda settings: FakeEmbeddingClient())

    result = check_models(configured_settings())

    assert result["status"] == "ok"
    assert result["llm"]["configured"] is True
    assert result["llm"]["available"] is True
    assert result["llm"]["model"] == "chat-test"
    assert result["embedding"]["configured"] is True
    assert result["embedding"]["available"] is True
    assert result["embedding"]["dimensions"] == 3


def test_check_llm_model_reports_missing_config():
    result = check_llm_model(Settings(base_url="", api_key="", model=""))

    assert result["configured"] is False
    assert result["available"] is False
    assert "BASE_URL" in result["message"]
    assert "API_KEY" in result["message"]
    assert "MODEL" in result["message"]


def test_check_embedding_model_reports_missing_config():
    result = check_embedding_model(Settings(base_url="https://chat.example.com/v1", api_key="chat-key", model="chat-test"))

    assert result["configured"] is False
    assert result["available"] is False
    assert result["dimensions"] == 0
    assert "EMBEDDING_BASE_URL" in result["message"]
