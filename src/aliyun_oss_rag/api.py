"""FastAPI application for Aliyun OSS Support RAG."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import AliyunOssAgent
from .config import get_logger, get_settings
from .data_loader import load_jsonl
from .model_checks import check_models
from .schemas import AskRequest, AskResponse, KnowledgeChunk, LookupRequest
from .tools import OSS_TOOLS


app = FastAPI(title="Aliyun OSS Support RAG Agent", version="0.1.0")
agent = AliyunOssAgent()
logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
API_PREFIXES = {"ask", "sources", "documents", "topics", "lookup", "health", "models", "docs", "redoc", "openapi.json"}


def _json_default(value: object) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def _sse_event(payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return f"data: {data}\n\n"


def _frontend_index():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return HTMLResponse(
        """
        <html lang="zh-CN">
          <head><meta charset="utf-8"><title>Aliyun OSS Support RAG</title></head>
          <body style="font-family: system-ui, sans-serif; margin: 48px;">
            <h1>Aliyun OSS Support RAG 前端尚未构建</h1>
            <p>请在项目根目录运行：</p>
            <pre>cd frontend
npm install
npm run build</pre>
            <p>然后重新启动 FastAPI，访问 <code>http://127.0.0.1:8000</code>。</p>
          </body>
        </html>
        """,
        status_code=503,
    )


@app.get("/health")
def health() -> dict[str, str | int]:
    settings = get_settings()
    return {
        "status": "ok",
        "chunks": len(agent.retriever.chunks),
        "documents": len(OSS_TOOLS.documents),
        "model": settings.model,
        "product": "Alibaba Cloud OSS",
        "retrieval_mode": "hybrid_dense_vector_bm25" if agent.retriever.embedding_client else "bm25_fallback",
        "vector_index_enabled": int(bool(agent.retriever.vector_by_chunk_id)),
    }


@app.get("/models/status")
def model_status() -> dict[str, Any]:
    return check_models()


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    logger.info("api_ask question=%s conversation_id=%s", request.question, request.conversation_id)
    return agent.run(request.question, request.conversation_id)


@app.post("/ask/stream")
def ask_stream(request: AskRequest) -> StreamingResponse:
    logger.info("api_ask_stream question=%s conversation_id=%s", request.question, request.conversation_id)

    def events() -> Iterator[str]:
        for event in agent.stream(request.question):
            yield _sse_event(event)
        yield _sse_event({"type": "done"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sources")
def sources() -> list[dict[str, object]]:
    chunks = load_jsonl(get_settings().chunks_path, KnowledgeChunk)
    seen: dict[str, dict[str, object]] = {}
    for chunk in chunks:
        seen[chunk.url] = {
            "source_title": chunk.source_title,
            "url": chunk.url,
            "source_type": chunk.source_type,
            "product": chunk.product,
            "category": chunk.category,
        }
    return list(seen.values())


@app.get("/documents")
def documents() -> list[dict[str, object]]:
    return [
        {
            "id": doc.id,
            "title": doc.title,
            "product": doc.product,
            "category": doc.category,
            "doc_type": doc.doc_type,
            "tags": doc.tags,
            "related_apis": doc.related_apis,
            "common_errors": doc.common_errors,
            "summary": doc.summary,
            "url": doc.url,
        }
        for doc in OSS_TOOLS.documents
    ]


@app.get("/documents/{document_id}")
def document_detail(document_id: str) -> dict[str, object]:
    result = OSS_TOOLS.lookup_document(document_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("message", "document not found"))
    return result


@app.get("/topics")
def topics() -> list[dict[str, object]]:
    path = get_settings().topics_path
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/lookup")
def lookup(request: LookupRequest) -> dict[str, object]:
    logger.info("api_lookup query=%s", request.query)
    return OSS_TOOLS.filter_by_topic(request.query)


app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def frontend_root():
    return _frontend_index()


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_fallback(full_path: str):
    first_segment = full_path.split("/", 1)[0]
    if first_segment in API_PREFIXES:
        raise HTTPException(status_code=404)
    candidate = FRONTEND_DIST / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return _frontend_index()
