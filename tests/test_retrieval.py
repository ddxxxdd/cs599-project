import json

from aliyun_oss_rag.config import Settings
from aliyun_oss_rag.retrieval import HybridRetriever
from aliyun_oss_rag.schemas import KnowledgeChunk


def test_retriever_returns_access_denied_troubleshooting_content():
    retriever = HybridRetriever()
    results = retriever.search("OSS 403 AccessDenied 权限 Bucket Policy RAM", top_k=5)
    assert results
    assert any("AccessDenied" in chunk.text and "RAM" in chunk.text for chunk, _score in results)


def test_retriever_returns_sts_content():
    retriever = HybridRetriever()
    results = retriever.search("STS 临时访问凭证 浏览器 上传 OSS", top_k=5)
    assert results
    assert any("临时凭证" in chunk.text or "AssumeRole" in chunk.text for chunk, _score in results)


def test_retriever_returns_api_content():
    retriever = HybridRetriever()
    results = retriever.search("PutObject GetObject API 参数 权限", top_k=5)
    assert results
    assert any("PutObject" in chunk.text and "GetObject" in chunk.text for chunk, _score in results)


def test_retriever_uses_vector_index_when_embedding_is_configured(tmp_path, monkeypatch):
    vector_index_path = tmp_path / "vector_index.json"
    vector_index_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "embedding_model": "fake-embedding",
                "dimensions": 2,
                "chunks": [
                    {"chunk_id": "oss-vector-a", "vector": [1.0, 0.0]},
                    {"chunk_id": "oss-vector-b", "vector": [0.0, 1.0]},
                ],
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(
        base_url="https://llm.example.com/v1",
        api_key="llm-key",
        model="llm-model",
        embedding_base_url="https://embedding.example.com/v1",
        embedding_api_key="embedding-key",
        embedding_model="fake-embedding",
        vector_index_path=vector_index_path,
    )

    class FakeEmbeddingClient:
        def embed(self, texts):
            return [[0.0, 1.0] for _text in texts]

    monkeypatch.setattr("aliyun_oss_rag.retrieval.get_settings", lambda: settings)
    monkeypatch.setattr("aliyun_oss_rag.retrieval.get_embedding_client", lambda _settings: FakeEmbeddingClient())

    chunks = [
        KnowledgeChunk(
            id="oss-vector-a",
            title="A",
            source_title="阿里云 OSS 官方文档",
            url="https://www.alibabacloud.com/help/zh/oss/",
            source_type="oss_test",
            tags=[],
            text="alpha",
            category="测试",
        ),
        KnowledgeChunk(
            id="oss-vector-b",
            title="B",
            source_title="阿里云 OSS 官方文档",
            url="https://www.alibabacloud.com/help/zh/oss/",
            source_type="oss_test",
            tags=[],
            text="beta",
            category="测试",
        ),
    ]

    results = HybridRetriever(chunks=chunks).search("semantic query", top_k=1)

    assert results[0][0].id == "oss-vector-b"
    assert results[0][1] > 0
