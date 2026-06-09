from aliyun_oss_rag.agent import AliyunOssAgent


class FailingLLM:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("401 Client Error: Unauthorized")

    def stream_events(self, prompt: str):
        raise RuntimeError("401 Client Error: Unauthorized")
        yield


def test_permission_question_calls_permission_tool():
    agent = AliyunOssAgent()
    response = agent.run("如何用 STS 临时访问凭证让浏览器上传 OSS？")
    assert response.intent == "permission"
    assert any(call.name == "permission_lookup" for call in response.tool_calls)
    assert any("sts" in citation.chunk_id for citation in response.citations)


def test_troubleshooting_question_calls_troubleshoot_tool():
    agent = AliyunOssAgent()
    response = agent.run("OSS 403 AccessDenied 应该怎么排查？")
    assert response.intent == "troubleshooting"
    assert any(call.name == "troubleshoot_lookup" for call in response.tool_calls)
    assert any("AccessDenied" in citation.snippet or "403" in citation.snippet for citation in response.citations)


def test_citations_cover_all_numbered_prompt_sources():
    agent = AliyunOssAgent()
    response = agent.run("OSS 403 AccessDenied 应该怎么排查？")
    assert len(response.citations) == 7
    assert all(citation.score != 999.0 for citation in response.citations)
    assert "[7]" in response.answer


def test_api_question_calls_api_tool():
    agent = AliyunOssAgent()
    response = agent.run("PutObject 需要什么权限，常见参数要注意什么？")
    assert response.intent == "api_reference"
    assert any(call.name == "api_lookup" for call in response.tool_calls)
    assert any("PutObject" in citation.snippet for citation in response.citations)


def test_streaming_answer_emits_metadata_and_tokens():
    agent = AliyunOssAgent()
    events = list(agent.stream("SignatureDoesNotMatch 常见原因有哪些？"))
    assert events[0]["type"] == "status"
    assert any(event["type"] == "meta" and event["state"]["intent"] == "troubleshooting" for event in events)
    assert any(event["type"] == "token" for event in events[1:])
    assert events[-1]["type"] == "final"
    assert "答案" in "".join(event.get("delta", "") for event in events if event["type"] == "token")


def test_streaming_llm_error_returns_final_event():
    agent = AliyunOssAgent()
    agent.llm = FailingLLM()
    events = list(agent.stream("OSS 403 AccessDenied 应该怎么排查？"))
    assert events[-1]["type"] == "final"
    assert "模型接口调用失败" in events[-1]["content"]
    assert events[-1]["state"]["error"]
