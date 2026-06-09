"""Build the Aliyun OSS support RAG knowledge base."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aliyun_oss_rag.config import PROCESSED_DIR, RAW_DIR, get_settings  # noqa: E402
from aliyun_oss_rag.embeddings import get_embedding_client  # noqa: E402
from aliyun_oss_rag.schemas import KnowledgeChunk, SupportDocument  # noqa: E402


def load_documents() -> list[SupportDocument]:
    path = RAW_DIR / "aliyun_oss_docs.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [SupportDocument.model_validate(row) for row in rows]


def chunk_text(
    base_id: str,
    title: str,
    source_title: str,
    url: str,
    source_type: str,
    tags: list[str],
    text: str,
    product: str,
    category: str,
    doc_type: str,
    section: str,
    limit: int = 720,
) -> list[KnowledgeChunk]:
    sentences = re.split(r"(?<=[。！？.!?])", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) > limit and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        chunks.append(current.strip())

    return [
        KnowledgeChunk(
            id=f"{base_id}-{idx:02d}",
            title=title,
            source_title=source_title,
            url=url,
            source_type=source_type,
            tags=tags,
            text=chunk,
            product=product,
            category=category,
            doc_type=doc_type,
            section=section,
        )
        for idx, chunk in enumerate(chunks, 1)
        if chunk
    ]


def build_chunks(documents: list[SupportDocument]) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for doc in documents:
        base_tags = [doc.product, doc.category, doc.doc_type, *doc.tags, *doc.related_apis, *doc.common_errors]
        overview_text = (
            f"{doc.title}。产品：{doc.product}。分类：{doc.category}。"
            f"文档类型：{doc.doc_type}。摘要：{doc.summary}"
            f"相关 API：{'、'.join(doc.related_apis) if doc.related_apis else '无'}。"
            f"常见错误：{'、'.join(doc.common_errors) if doc.common_errors else '无'}。"
        )
        chunks.extend(
            chunk_text(
                f"{doc.id}-overview",
                f"{doc.title}-概览",
                doc.source_title,
                doc.url,
                "oss_document_overview",
                [*base_tags, "概览", "官方文档"],
                overview_text,
                doc.product,
                doc.category,
                doc.doc_type,
                "概览",
            )
        )
        for idx, section in enumerate(doc.sections, 1):
            section_tags = [*base_tags, section.kind, section.heading, *section.tags]
            section_text = f"{doc.title} / {section.heading}：{section.content}"
            chunks.extend(
                chunk_text(
                    f"{doc.id}-{section.kind}-{idx:02d}",
                    f"{doc.title}-{section.heading}",
                    doc.source_title,
                    doc.url,
                    f"oss_{section.kind}",
                    section_tags,
                    section_text,
                    doc.product,
                    doc.category,
                    doc.doc_type,
                    section.heading,
                )
            )
    return chunks


def build_document_index(documents: list[SupportDocument]) -> list[dict[str, object]]:
    return [
        {
            "id": doc.id,
            "title": doc.title,
            "product": doc.product,
            "category": doc.category,
            "doc_type": doc.doc_type,
            "url": doc.url,
            "tags": doc.tags,
            "related_apis": doc.related_apis,
            "common_errors": doc.common_errors,
            "summary": doc.summary,
        }
        for doc in documents
    ]


def build_topics(documents: list[SupportDocument]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    doc_counts: dict[str, int] = defaultdict(int)
    for doc in documents:
        doc_counts[doc.category] += 1
        grouped.setdefault(
            doc.category,
            {
                "id": re.sub(r"[^a-zA-Z0-9]+", "-", doc.category).strip("-").lower() or doc.category,
                "name": doc.category,
                "product": doc.product,
                "doc_count": 0,
                "tags": set(),
            },
        )
        grouped[doc.category]["tags"].update(doc.tags)  # type: ignore[union-attr]
    topics = []
    for category, topic in grouped.items():
        topics.append(
            {
                "id": topic["id"],
                "name": topic["name"],
                "product": topic["product"],
                "doc_count": doc_counts[category],
                "tags": sorted(topic["tags"]),  # type: ignore[arg-type]
            }
        )
    return sorted(topics, key=lambda item: str(item["name"]))


def chunk_embedding_text(chunk: KnowledgeChunk) -> str:
    return "\n".join(
        [
            chunk.title,
            f"产品：{chunk.product}",
            f"分类：{chunk.category}",
            f"章节：{chunk.section}",
            f"标签：{'、'.join(chunk.tags)}",
            chunk.text,
        ]
    )


def build_vector_index(chunks: list[KnowledgeChunk], batch_size: int = 16) -> dict[str, object]:
    settings = get_settings()
    if not settings.embedding_configured:
        return {
            "enabled": False,
            "reason": "EMBEDDING_BASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL are not configured.",
            "embedding_model": "",
            "dimensions": 0,
            "chunks": [],
        }

    client = get_embedding_client(settings)
    rows: list[dict[str, object]] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = client.embed(chunk_embedding_text(chunk) for chunk in batch)
        for chunk, vector in zip(batch, vectors):
            rows.append({"chunk_id": chunk.id, "vector": vector})

    dimensions = len(rows[0]["vector"]) if rows else 0
    return {
        "enabled": True,
        "embedding_model": settings.embedding_model,
        "dimensions": dimensions,
        "chunks": rows,
    }


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    documents = load_documents()
    chunks = build_chunks(documents)
    chunks_path = PROCESSED_DIR / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(chunk.model_dump_json(ensure_ascii=False) + "\n")

    (PROCESSED_DIR / "documents_index.json").write_text(
        json.dumps(build_document_index(documents), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (PROCESSED_DIR / "topics_manifest.json").write_text(
        json.dumps(build_topics(documents), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    vector_index = build_vector_index(chunks)
    (PROCESSED_DIR / "vector_index.json").write_text(
        json.dumps(vector_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    index = {
        "chunk_count": len(chunks),
        "document_count": len(documents),
        "topic_count": len({doc.category for doc in documents}),
        "product": "Alibaba Cloud OSS",
        "retrieval": "hybrid_dense_vector_bm25",
        "vector_index_enabled": bool(vector_index["enabled"]),
        "embedding_model": vector_index.get("embedding_model", ""),
        "sources": sorted({chunk.source_title for chunk in chunks}),
        "generated_by": "scripts/build_kb.py",
        "note": "Knowledge-base chunks contain curated Aliyun OSS support document summaries with official source URLs. Dense vector retrieval is enabled after configuring embedding environment variables and rebuilding the KB.",
    }
    (PROCESSED_DIR / "retrieval_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built {len(chunks)} OSS support chunks at {chunks_path}")


if __name__ == "__main__":
    main()
