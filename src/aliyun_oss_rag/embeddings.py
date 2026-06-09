"""OpenAI-compatible embedding client for dense retrieval."""

from __future__ import annotations

from collections.abc import Iterable

import requests

from .config import Settings, get_logger, get_settings


logger = get_logger(__name__)


def embeddings_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/embeddings"):
        return base
    if base.endswith("/v1"):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"


class EmbeddingClient:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        missing = [
            name
            for name, value in {
                "EMBEDDING_BASE_URL": base_url,
                "EMBEDDING_API_KEY": api_key,
                "EMBEDDING_MODEL": model,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing embedding environment variables: {', '.join(missing)}")
        self.api_key = api_key
        self.model = model
        self.endpoint = embeddings_endpoint(base_url)
        logger.info("embedding_client_ready model=%s endpoint=%s", self.model, self.endpoint)

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        items = [text for text in texts]
        if not items:
            return []
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": items},
            timeout=(10, 120),
        )
        response.raise_for_status()
        data = response.json()
        rows = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [row["embedding"] for row in rows]
        if len(vectors) != len(items):
            raise ValueError(f"Embedding response count mismatch: expected {len(items)}, got {len(vectors)}")
        return vectors


def get_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    settings = settings or get_settings()
    return EmbeddingClient(
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
    )
