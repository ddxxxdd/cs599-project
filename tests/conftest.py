import pytest


class FakeLLM:
    def generate(self, prompt: str) -> str:
        return f"{prompt}\n答案：以上内容来自 OSS 检索资料。"

    def stream_events(self, prompt: str):
        yield {"type": "content", "content": "答案："}
        yield {"type": "content", "content": "以上内容来自 OSS 检索资料。"}


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setattr("aliyun_oss_rag.agent.get_llm", lambda settings=None: FakeLLM())
