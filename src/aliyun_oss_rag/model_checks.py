"""Runtime connectivity checks for configured model providers."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import requests

from .config import Settings, get_settings
from .embeddings import embeddings_endpoint, get_embedding_client
from .llm import chat_completions_endpoint, get_llm


def _elapsed_ms(start: float) -> int:
    return int(round((perf_counter() - start) * 1000))


def _error_detail(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}: {exc.response.reason or 'request failed'}"
    return f"{exc.__class__.__name__}: {exc}"


def _missing_detail(names: list[str]) -> str:
    return f"Missing environment variables: {', '.join(names)}"


def check_llm_model(settings: Settings | None = None) -> dict[str, Any]:
    """Call the configured chat model once and report whether it responds."""
    settings = settings or get_settings()
    endpoint = chat_completions_endpoint(settings.base_url) if settings.base_url else ""
    missing = [
        name
        for name, value in {
            "BASE_URL": settings.base_url,
            "API_KEY": settings.api_key,
            "MODEL": settings.model,
        }.items()
        if not value
    ]
    result: dict[str, Any] = {
        "configured": not missing,
        "available": False,
        "model": settings.model,
        "endpoint": endpoint,
        "latency_ms": None,
        "message": "not checked",
    }
    if missing:
        result["message"] = _missing_detail(missing)
        return result

    start = perf_counter()
    try:
        client = get_llm(settings)
        answer = client.generate("模型连通性测试。请只回复 OK。")
        result["latency_ms"] = _elapsed_ms(start)
        result["available"] = bool(answer.strip())
        result["message"] = "ok" if result["available"] else "model returned an empty response"
    except Exception as exc:
        result["latency_ms"] = _elapsed_ms(start)
        result["message"] = _error_detail(exc)
    return result


def check_embedding_model(settings: Settings | None = None) -> dict[str, Any]:
    """Call the configured embedding model once and report vector dimensions."""
    settings = settings or get_settings()
    endpoint = embeddings_endpoint(settings.embedding_base_url) if settings.embedding_base_url else ""
    missing = [
        name
        for name, value in {
            "EMBEDDING_BASE_URL": settings.embedding_base_url,
            "EMBEDDING_API_KEY": settings.embedding_api_key,
            "EMBEDDING_MODEL": settings.embedding_model,
        }.items()
        if not value
    ]
    result: dict[str, Any] = {
        "configured": not missing,
        "available": False,
        "model": settings.embedding_model,
        "endpoint": endpoint,
        "latency_ms": None,
        "dimensions": 0,
        "message": "not checked",
    }
    if missing:
        result["message"] = _missing_detail(missing)
        return result

    start = perf_counter()
    try:
        client = get_embedding_client(settings)
        vectors = client.embed(["OSS RAG embedding connectivity test"])
        vector = vectors[0] if vectors else []
        result["latency_ms"] = _elapsed_ms(start)
        result["dimensions"] = len(vector)
        result["available"] = bool(vector)
        result["message"] = "ok" if result["available"] else "embedding model returned no vector"
    except Exception as exc:
        result["latency_ms"] = _elapsed_ms(start)
        result["message"] = _error_detail(exc)
    return result


def check_models(settings: Settings | None = None) -> dict[str, Any]:
    """Return a combined runtime status for the chat and embedding models."""
    settings = settings or get_settings()
    llm = check_llm_model(settings)
    embedding = check_embedding_model(settings)
    ok = bool(llm["available"] and embedding["available"])
    return {
        "status": "ok" if ok else "degraded",
        "llm": llm,
        "embedding": embedding,
    }
