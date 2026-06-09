import os

from fastapi.testclient import TestClient

os.environ.setdefault("BASE_URL", "http://example.test/v1")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("MODEL", "test-model")

from aliyun_oss_rag import api as api_module


class FakeLLM:
    def generate(self, prompt: str) -> str:
        return "答案：OSS 403 AccessDenied 通常需要检查 RAM Policy、Bucket Policy、ACL、STS 凭证和签名。"

    def stream_events(self, prompt: str):
        yield {"type": "reasoning", "content": "整理 OSS 文档"}
        for chunk in ("答案：", "请检查 RAM Policy、Bucket Policy 和 STS 凭证。"):
            yield {"type": "content", "content": chunk}


api_module.agent.llm = FakeLLM()
app = api_module.app
client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["product"] == "Alibaba Cloud OSS"
    assert body["documents"] >= 10


def test_model_status_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "check_models",
        lambda: {
            "status": "ok",
            "llm": {"configured": True, "available": True, "model": "chat-test"},
            "embedding": {"configured": True, "available": True, "model": "embedding-test", "dimensions": 768},
        },
    )

    response = client.get("/models/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm"]["available"] is True
    assert body["embedding"]["dimensions"] == 768


def test_ask_endpoint():
    response = client.post("/ask", json={"question": "OSS 403 AccessDenied 应该怎么排查？"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "troubleshooting"
    assert "AccessDenied" in body["answer"]
    assert body["citations"][0]["snippet"]


def test_ask_stream_endpoint():
    with client.stream("POST", "/ask/stream", json={"question": "如何用 STS 临时凭证上传 OSS？"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        body = "".join(response.iter_text())
    assert '"type": "status"' in body
    assert '"type": "meta"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body


def test_documents_topics_and_lookup_endpoints():
    documents = client.get("/documents")
    assert documents.status_code == 200
    assert len(documents.json()) >= 10

    detail = client.get("/documents/oss-sts-temporary-credentials")
    assert detail.status_code == 200
    assert detail.json()["document"]["id"] == "oss-sts-temporary-credentials"

    topics = client.get("/topics")
    assert topics.status_code == 200
    assert topics.json()

    lookup = client.post("/lookup", json={"query": "Bucket Policy 权限"})
    assert lookup.status_code == 200
    assert lookup.json()["count"] > 0
