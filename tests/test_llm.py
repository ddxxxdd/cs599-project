from aliyun_oss_rag.llm import LLMClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, chunk_size: int, decode_unicode: bool):
        yield 'data: {"choices":[{"delta":{"reasoning_content":"整理资料"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"答案："}}]}'
        yield 'data: {"choices":[{"delta":{"content":"OSS 403 需要检查权限。"}}]}'
        yield "data: [DONE]"


def test_llm_stream_events_parse_sse(monkeypatch):
    def fake_post(endpoint, headers, json, timeout, stream):
        assert endpoint == "http://example.test/v1/chat/completions"
        assert headers["Accept"] == "text/event-stream"
        assert json["stream"] is True
        assert stream is True
        return FakeResponse()

    monkeypatch.setattr("aliyun_oss_rag.llm.requests.post", fake_post)

    client = LLMClient(api_key="test-key", model="test-model", base_url="http://example.test/v1")
    events = list(client.stream_events("OSS 403 怎么排查"))

    assert events == [
        {"type": "reasoning", "content": "整理资料"},
        {"type": "content", "content": "答案："},
        {"type": "content", "content": "OSS 403 需要检查权限。"},
    ]
