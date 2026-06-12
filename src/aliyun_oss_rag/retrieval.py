"""Hybrid dense-vector and BM25 retriever for OSS support RAG."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict

from .config import get_logger, get_settings
from .data_loader import load_jsonl
from .embeddings import get_embedding_client
from .schemas import KnowledgeChunk


WORD_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")
logger = get_logger(__name__)


def tokenize(text: str) -> list[str]:
    parts = WORD_RE.findall(text.lower())
    cjk_chars = [p for p in parts if re.fullmatch(r"[\u4e00-\u9fff]", p)]
    tokens = parts[:]
    tokens.extend("".join(cjk_chars[i : i + 2]) for i in range(max(0, len(cjk_chars) - 1)))
    return [token for token in tokens if token.strip()]


class HybridRetriever:
    """Hybrid dense-vector + BM25 retriever with graceful lexical fallback."""

    def __init__(self, chunks: list[KnowledgeChunk] | None = None) -> None:
        self.settings = get_settings()
        self.chunks = chunks if chunks is not None else load_jsonl(self.settings.chunks_path, KnowledgeChunk)
        logger.info("knowledge_base_loaded chunks=%s path=%s", len(self.chunks), self.settings.chunks_path)
        self.doc_tokens = [tokenize(" ".join([c.title, c.category, c.section, " ".join(c.tags), c.text])) for c in self.chunks]
        # 预计算每个 chunk 的词频与文档长度，避免每次查询重复构建 Counter。
        self.doc_counters = [Counter(tokens) for tokens in self.doc_tokens]
        self.doc_freq: dict[str, int] = defaultdict(int)
        for tokens in self.doc_tokens:
            for token in set(tokens):
                self.doc_freq[token] += 1
        self.avg_len = sum(len(tokens) for tokens in self.doc_tokens) / max(1, len(self.doc_tokens))
        self.chunk_by_id = {chunk.id: chunk for chunk in self.chunks}
        self.vector_by_chunk_id = self._load_vector_index()
        # 预计算向量模长，查询时只需计算点积，降低单次检索开销。
        self.vector_norms = {
            chunk_id: math.sqrt(sum(value * value for value in vector)) or 1.0
            for chunk_id, vector in self.vector_by_chunk_id.items()
        }
        self.embedding_client = None
        if self.vector_by_chunk_id and self.settings.embedding_configured:
            try:
                self.embedding_client = get_embedding_client(self.settings)
            except Exception:
                logger.exception("embedding_client_init_failed")
        logger.info(
            "retriever_ready mode=%s vectors=%s",
            "hybrid_dense_vector_bm25" if self.embedding_client else "bm25_fallback",
            len(self.vector_by_chunk_id),
        )

    def _load_vector_index(self) -> dict[str, list[float]]:
        path = self.settings.vector_index_path
        if not path.exists():
            logger.info("vector_index_missing path=%s", path)
            return {}
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.exception("vector_index_invalid_json path=%s", path)
            return {}
        if not index.get("enabled"):
            logger.info("vector_index_disabled reason=%s", index.get("reason", "not configured"))
            return {}
        rows = index.get("chunks", [])
        return {
            str(row["chunk_id"]): [float(value) for value in row["vector"]]
            for row in rows
            if row.get("chunk_id") and row.get("vector")
        }

    def _bm25_scores(self, query: str) -> dict[str, float]:
        q_tokens = tokenize(query)
        q_counts = Counter(q_tokens)
        scores: dict[str, float] = {}
        total_docs = len(self.chunks)
        for chunk, tokens, counts in zip(self.chunks, self.doc_tokens, self.doc_counters):
            doc_len = len(tokens) or 1
            score = 0.0
            for token, q_count in q_counts.items():
                if token not in counts:
                    continue
                idf = math.log(1 + (total_docs - self.doc_freq[token] + 0.5) / (self.doc_freq[token] + 0.5))
                tf = counts[token]
                score += idf * ((tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * doc_len / self.avg_len))) * q_count
            if any(tag in query for tag in chunk.tags):
                score += 1.2
            if score > 0:
                scores[chunk.id] = round(score, 4)
        return scores

    def _vector_scores(self, query: str) -> dict[str, float]:
        if not self.embedding_client or not self.vector_by_chunk_id:
            return {}
        try:
            query_vector = self.embedding_client.embed([query])[0]
        except Exception:
            logger.exception("query_embedding_failed")
            return {}
        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        expected_dim = len(query_vector)
        scores: dict[str, float] = {}
        for chunk_id, vector in self.vector_by_chunk_id.items():
            if len(vector) != expected_dim:
                # 维度不一致（例如更换 Embedding 模型后未重建索引）时跳过，避免产生错误相似度。
                logger.warning("vector_dim_mismatch chunk_id=%s expected=%s got=%s", chunk_id, expected_dim, len(vector))
                continue
            dot = sum(left * right for left, right in zip(query_vector, vector))
            scores[chunk_id] = dot / (query_norm * self.vector_norms.get(chunk_id, 1.0))
        return scores

    def _normalize(self, scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        values = list(scores.values())
        min_score = min(values)
        max_score = max(values)
        if math.isclose(max_score, min_score):
            return {key: 1.0 for key in scores}
        return {key: (value - min_score) / (max_score - min_score) for key, value in scores.items()}

    def search(self, query: str, top_k: int = 5) -> list[tuple[KnowledgeChunk, float]]:
        logger.info("rag_search_start top_k=%s query=%s", top_k, query)
        if not query or not query.strip() or top_k <= 0:
            logger.warning("rag_search_invalid_input query_empty=%s top_k=%s", not (query and query.strip()), top_k)
            return []
        if not self.chunks:
            logger.warning("rag_search_empty_index")
            return []
        bm25_scores = self._bm25_scores(query)
        vector_scores = self._vector_scores(query)
        bm25_normalized = self._normalize(bm25_scores)
        vector_normalized = self._normalize(vector_scores)
        candidate_ids = set(bm25_normalized) | set(vector_normalized)
        scored = []
        for chunk_id in candidate_ids:
            chunk = self.chunk_by_id.get(chunk_id)
            if chunk is None:
                # 向量索引可能包含已删除/过期 chunk，跳过避免 KeyError。
                continue
            bm25_part = bm25_normalized.get(chunk_id, 0.0)
            vector_part = vector_normalized.get(chunk_id, 0.0)
            score = 0.45 * bm25_part + 0.55 * vector_part if vector_normalized else bm25_part
            if score > 0:
                scored.append((chunk, round(score, 4)))
        results = sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]
        logger.info(
            "rag_search_done hits=%s mode=%s top_chunks=%s",
            len(results),
            "hybrid" if vector_normalized else "bm25",
            [chunk.id for chunk, _score in results[:3]],
        )
        return results


def format_context(results: list[tuple[KnowledgeChunk, float]]) -> str:
    lines = []
    for idx, (chunk, score) in enumerate(results, 1):
        lines.append(
            f"[{idx}] {chunk.title} ({chunk.source_title}, {chunk.product}/{chunk.category}/{chunk.section}, score={score})\n"
            f"{chunk.text}\n来源链接：{chunk.url}"
        )
    return "\n\n".join(lines)
