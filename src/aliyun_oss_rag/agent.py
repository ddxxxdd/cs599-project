"""LangGraph-powered Aliyun OSS technical support Agent."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Literal, TypedDict

from .config import get_logger, get_settings
from .llm import get_llm
from .retrieval import HybridRetriever, format_context
from .schemas import AskResponse, Citation, Intent, ToolCall
from .tools import OSS_TOOLS


API_TERMS = ("api", "接口", "参数", "返回", "putobject", "getobject", "list", "deleteobject", "openapi")
PERMISSION_TERMS = ("权限", "授权", "ram", "sts", "policy", "accesskey", "角色", "临时凭证", "bucket policy")
TROUBLE_TERMS = ("报错", "错误", "失败", "403", "404", "accessdenied", "signaturedoesnotmatch", "nosuchkey", "nosuchbucket", "排查")
COST_TERMS = ("费用", "成本", "计费", "生命周期", "低频", "归档", "冷归档", "存储类型")
DOC_QUESTION_RE = re.compile(r"(怎么|如何|为什么|区别|配置|设置|使用|排查|需要|是什么|有什么|步骤|最佳实践|限制)")
logger = get_logger(__name__)
# 最终送入提示词并展示为“知识库依据”的片段数（top-5）。
CONTEXT_CHUNK_LIMIT = 5
# 混合检索候选池大小：先多召回一些，供工具结果优先级重排后再截断为 CONTEXT_CHUNK_LIMIT。
RETRIEVAL_CANDIDATE_K = 8


class AgentState(TypedDict, total=False):
    question: str
    intent: Intent
    retrieved: list[tuple[Any, float]]
    tool_calls: list[ToolCall]
    answer: str
    error: str
    citations: list[Citation]
    suggestions: list[str]
    prompt: str


class AgentStreamEvent(TypedDict, total=False):
    type: Literal["status", "meta", "reasoning", "token", "final"]
    state: AgentState
    content: str
    delta: str


class AliyunOssAgent:
    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.llm = get_llm(get_settings())
        self.tools = OSS_TOOLS
        self.graph = self._build_graph()
        logger.info("oss_agent_ready langgraph=%s", bool(self.graph))

    def _build_graph(self) -> Any | None:
        try:
            from langgraph.graph import END, StateGraph

            graph = StateGraph(AgentState)
            graph.add_node("classify", self._classify)
            graph.add_node("retrieve", self._retrieve)
            graph.add_node("tools", self._tools)
            graph.add_node("synthesize", self._synthesize)
            graph.set_entry_point("classify")
            graph.add_edge("classify", "retrieve")
            graph.add_edge("retrieve", "tools")
            graph.add_edge("tools", "synthesize")
            graph.add_edge("synthesize", END)
            return graph.compile()
        except Exception:
            logger.exception("langgraph_build_failed")
            return None

    def run(self, question: str, conversation_id: str | None = None) -> AskResponse:
        logger.info("agent_run_start question=%s conversation_id=%s", question, conversation_id)
        result = self._prepare_response(question)
        try:
            result["answer"] = self.llm.generate(result["prompt"])
        except Exception as exc:
            logger.exception("agent_llm_generate_failed")
            result["answer"] = f"模型接口调用失败：{exc}。请检查 .env 中的 BASE_URL、API_KEY、MODEL 是否有效。"
            result["error"] = str(exc)
        logger.info(
            "agent_run_done intent=%s citations=%s tool_calls=%s",
            result["intent"],
            len(result.get("citations", [])),
            [call.name for call in result.get("tool_calls", [])],
        )
        return AskResponse(
            question=question,
            answer=result["answer"],
            intent=result["intent"],
            citations=result.get("citations", []),
            tool_calls=result.get("tool_calls", []),
            suggestions=result.get("suggestions", []),
        )

    def stream(self, question: str) -> Iterator[AgentStreamEvent]:
        logger.info("agent_stream_start question=%s", question)
        yield {"type": "status", "content": "正在检索阿里云 OSS 技术支持知识库"}
        state = self._prepare_response(question)
        yield {
            "type": "status",
            "content": f"已检索到 {len(state.get('citations', []))} 条 OSS 文档片段，正在连接大模型",
        }
        yield {"type": "meta", "state": self._public_state(state)}
        answer = ""
        try:
            for event in self.llm.stream_events(state["prompt"]):
                if event["type"] == "reasoning":
                    yield {"type": "reasoning", "content": event.get("content", "")}
                else:
                    answer += event["content"]
                    yield {"type": "token", "content": event["content"], "delta": event["content"]}
        except Exception as exc:
            logger.exception("agent_llm_stream_failed")
            answer = f"模型接口调用失败：{exc}。请检查 .env 中的 BASE_URL、API_KEY、MODEL 是否有效。"
            state["error"] = str(exc)
            yield {"type": "status", "content": "模型接口调用失败，请检查模型配置"}
        state["answer"] = answer
        yield {"type": "final", "state": self._public_state(state), "content": answer}
        logger.info("agent_stream_done intent=%s citations=%s", state["intent"], len(state.get("citations", [])))

    def _public_state(self, state: AgentState) -> AgentState:
        """剔除 prompt、retrieved 等内部字段：避免向前端泄露完整提示词，并显著减小 SSE 负载。"""
        internal_keys = {"prompt", "retrieved"}
        return {key: value for key, value in state.items() if key not in internal_keys}  # type: ignore[return-value]

    def _prepare_response(self, question: str) -> AgentState:
        state: AgentState = {"question": question, "tool_calls": []}
        if self.graph:
            result = self.graph.invoke(dict(state))
        else:
            result = self._synthesize(self._tools(self._retrieve(self._classify(state))))
        return result

    def _classify(self, state: AgentState) -> AgentState:
        question = state["question"]
        lowered = question.lower()
        doc_matches = OSS_TOOLS.find_documents_in_text(question)
        if len(question.strip()) <= 3:
            state["intent"] = "smalltalk"
        elif any(term in lowered for term in TROUBLE_TERMS):
            state["intent"] = "troubleshooting"
        elif any(term in lowered for term in API_TERMS):
            state["intent"] = "api_reference"
        elif any(term in lowered for term in PERMISSION_TERMS):
            state["intent"] = "permission"
        elif any(term in lowered for term in COST_TERMS):
            state["intent"] = "cost"
        elif doc_matches and DOC_QUESTION_RE.search(question):
            state["intent"] = "doc_lookup"
        else:
            state["intent"] = "knowledge"
        logger.info("agent_classified intent=%s docs=%s", state["intent"], [doc.id for doc in doc_matches[:3]])
        return state

    def _retrieve(self, state: AgentState) -> AgentState:
        state["retrieved"] = self.retriever.search(state["question"], top_k=RETRIEVAL_CANDIDATE_K)
        return state

    def _tools(self, state: AgentState) -> AgentState:
        question = state["question"]
        calls: list[ToolCall] = list(state.get("tool_calls", []))
        doc_matches = OSS_TOOLS.find_documents_in_text(question)
        if state["intent"] == "troubleshooting":
            result = OSS_TOOLS.troubleshoot(question)
            calls.append(ToolCall(name="troubleshoot_lookup", arguments={"query": question}, result=result))
        elif state["intent"] == "api_reference":
            result = OSS_TOOLS.lookup_api(question)
            calls.append(ToolCall(name="api_lookup", arguments={"query": question}, result=result))
        elif state["intent"] == "permission":
            result = OSS_TOOLS.permission_guides(question)
            calls.append(ToolCall(name="permission_lookup", arguments={"query": question}, result=result))
        elif state["intent"] == "cost":
            result = OSS_TOOLS.filter_by_topic(question)
            calls.append(ToolCall(name="cost_lookup", arguments={"query": question}, result=result))
        elif doc_matches:
            for doc in doc_matches[:2]:
                result = OSS_TOOLS.lookup_document(doc.id)
                calls.append(ToolCall(name="doc_lookup", arguments={"query": doc.id}, result=result))
        else:
            result = OSS_TOOLS.filter_by_topic(question)
            calls.append(ToolCall(name="topic_lookup", arguments={"query": question}, result=result))
        state["tool_calls"] = calls
        logger.info("agent_tools_done calls=%s", [call.name for call in calls])
        return state

    def _synthesize(self, state: AgentState) -> AgentState:
        state["retrieved"] = self._prioritized_retrieval(state)
        # 先按工具优先级选出 top-N 片段，再按相关度从高到低排序；
        # 引用编号 [1..N] 与前端“知识库依据”因此都按相关度降序展示。
        context_results = sorted(
            state.get("retrieved", [])[:CONTEXT_CHUNK_LIMIT],
            key=lambda item: item[1],
            reverse=True,
        )
        citations = []
        for chunk, score in context_results:
            citations.append(
                Citation(
                    chunk_id=chunk.id,
                    title=chunk.title,
                    source_title=chunk.source_title,
                    url=chunk.url,
                    snippet=self._snippet(chunk.text),
                    score=float(score),
                    product=chunk.product,
                    category=chunk.category,
                    doc_type=chunk.doc_type,
                    section=chunk.section,
                )
            )
        context = format_context(context_results)
        prompt = (
            f"用户问题：{state['question']}\n\n"
            f"工具结果：{[call.model_dump() for call in state.get('tool_calls', [])]}\n\n"
            f"检索资料：\n{context}\n\n"
            "请作为企业云存储技术支持工程师回答。要求："
            "1. 只依据阿里云 OSS 知识库片段和工具结果回答；"
            "2. 给出可执行排查或配置步骤，必要时区分控制台、SDK、OpenAPI；"
            "3. 涉及权限必须说明 RAM、STS、Bucket Policy、ACL 或 KMS 的边界；"
            "4. 涉及错误码必须列出优先排查项；"
            f"5. 保留来源编号，只能引用检索资料中的 [1] 到 [{len(citations)}]；"
            "6. 如果资料不足，明确说明需要补充的日志、RequestId、Bucket、Endpoint 或错误码。"
        )
        state["prompt"] = prompt
        state["answer"] = ""
        state["citations"] = citations
        state["suggestions"] = self._suggestions(state)
        logger.info("agent_prompt_ready context_chunks=%s citations=%s", len(context_results), len(citations))
        return state

    def _snippet(self, text: str, limit: int = 200) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

    def _doc_chunk_ids(self, doc_id: str, question: str = "") -> list[str]:
        chunks = [chunk.id for chunk in self.retriever.chunks if chunk.id.startswith(f"{doc_id}-")]
        if any(term in question.lower() for term in TROUBLE_TERMS):
            chunks = sorted(chunks, key=lambda item: (0 if "-troubleshooting-" in item else 1, item))
        elif any(term in question.lower() for term in PERMISSION_TERMS):
            chunks = sorted(chunks, key=lambda item: (0 if "-auth-" in item else 1, item))
        elif any(term in question.lower() for term in API_TERMS):
            chunks = sorted(chunks, key=lambda item: (0 if "-api-" in item else 1, item))
        return chunks[:4]

    def _prioritized_retrieval(self, state: AgentState) -> list[tuple[Any, float]]:
        retrieved = list(state.get("retrieved", []))
        chunk_by_id = self.retriever.chunk_by_id
        score_by_chunk_id = {chunk.id: score for chunk, score in retrieved}
        fallback_score = max(score_by_chunk_id.values(), default=1.0)
        preferred_doc_ids: list[str] = []

        def prefer_document(doc: dict[str, Any] | None) -> None:
            if doc and doc.get("id"):
                doc_id = str(doc["id"])
                if doc_id not in preferred_doc_ids:
                    preferred_doc_ids.append(doc_id)

        for call in state.get("tool_calls", []):
            if call.name == "doc_lookup" and call.result.get("found"):
                prefer_document(call.result.get("document"))
            else:
                for item in call.result.get("matches", [])[:4]:
                    prefer_document(item)

        seen: set[str] = set()
        prioritized: list[tuple[Any, float]] = []
        for doc_id in preferred_doc_ids:
            doc_scores = [
                score
                for chunk, score in retrieved
                if chunk.id.startswith(f"{doc_id}-")
            ]
            preferred_score = max(doc_scores, default=fallback_score)
            for chunk_id in self._doc_chunk_ids(doc_id, state["question"]):
                chunk = chunk_by_id.get(chunk_id)
                if chunk and chunk.id not in seen:
                    prioritized.append((chunk, score_by_chunk_id.get(chunk.id, preferred_score)))
                    seen.add(chunk.id)
        for chunk, score in retrieved:
            if chunk.id not in seen:
                prioritized.append((chunk, score))
                seen.add(chunk.id)
        return prioritized

    def _suggestions(self, state: AgentState) -> list[str]:
        if state["intent"] == "troubleshooting":
            return ["OSS 403 AccessDenied 怎么排查", "SignatureDoesNotMatch 常见原因", "NoSuchKey 是对象不存在吗"]
        if state["intent"] == "permission":
            return ["如何用 STS 临时凭证上传 OSS", "RAM Policy 和 Bucket Policy 有什么区别", "如何限制用户只能读某个 Bucket 前缀"]
        if state["intent"] == "api_reference":
            return ["PutObject 需要哪些权限", "分片上传涉及哪些 API", "GetObject 私有 Bucket 如何下载"]
        return ["如何创建 Bucket 并上传 Object", "OSS 生命周期规则怎么降低成本", "浏览器直传 OSS 为什么跨域失败"]


OssRagAgent = AliyunOssAgent
