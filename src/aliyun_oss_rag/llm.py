"""OpenAI-compatible LLM client."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Literal, TypedDict

import requests

from .config import Settings, get_logger, get_settings


logger = get_logger(__name__)


class LLMStreamEvent(TypedDict):
    type: Literal["content", "reasoning"]
    content: str


def chat_completions_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


class LLMClient:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        missing = [name for name, value in {"BASE_URL": base_url, "API_KEY": api_key, "MODEL": model}.items() if not value]
        if missing:
            raise ValueError(f"Missing LLM environment variables: {', '.join(missing)}")
        self.api_key = api_key
        self.model = model
        self.endpoint = chat_completions_endpoint(base_url)
        logger.info("llm_client_ready model=%s endpoint=%s", self.model, self.endpoint)

    def _headers(self, stream: bool = False) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }

    def _payload(self, prompt: str, stream: bool = False) -> dict[str, object]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是严谨的阿里云 OSS 技术支持 RAG Agent。只基于给定 OSS 文档资料回答，并保留引用编号。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "stream": stream,
        }

    def generate(self, prompt: str) -> str:
        logger.info("llm_generate_start model=%s prompt_chars=%s", self.model, len(prompt))
        response = requests.post(self.endpoint, headers=self._headers(), json=self._payload(prompt), timeout=(10, 90))
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not content:
            raise ValueError(f"LLM 响应缺少内容：{json.dumps(data, ensure_ascii=False)[:200]}")
        answer = content.strip()
        logger.info("llm_generate_done answer_chars=%s", len(answer))
        return answer

    def _iter_sse_data(self, response: requests.Response) -> Iterator[str]:
        for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
            line = line.strip()
            if not line or line.startswith(("event:", "id:", "retry:")):
                continue
            if line.startswith("data:"):
                data = line.removeprefix("data:").strip()
                if data:
                    yield data
            elif line == "[DONE]" or line.startswith("{"):
                yield line

    def stream_events(self, prompt: str) -> Iterator[LLMStreamEvent]:
        logger.info("llm_stream_start model=%s prompt_chars=%s", self.model, len(prompt))
        content_chunks = 0
        reasoning_chunks = 0
        with requests.post(
            self.endpoint,
            headers=self._headers(stream=True),
            json=self._payload(prompt, stream=True),
            timeout=(10, 120),
            stream=True,
        ) as response:
            response.raise_for_status()
            for data in self._iter_sse_data(response):
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or choice.get("message") or {}
                content = delta.get("content")
                if content:
                    content_chunks += 1
                    yield {"type": "content", "content": content}
                elif reasoning_content := delta.get("reasoning_content"):
                    reasoning_chunks += 1
                    yield {"type": "reasoning", "content": str(reasoning_content)}
        logger.info("llm_stream_done content_chunks=%s reasoning_chunks=%s", content_chunks, reasoning_chunks)

    def stream(self, prompt: str) -> Iterator[str]:
        for event in self.stream_events(prompt):
            if event["type"] == "content":
                yield event["content"]


def get_llm(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    return LLMClient(api_key=settings.api_key, model=settings.model, base_url=settings.base_url)
