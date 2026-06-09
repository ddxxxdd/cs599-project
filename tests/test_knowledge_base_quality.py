import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_support_documents_are_complete():
    docs = json.loads((PROJECT_ROOT / "data" / "raw" / "aliyun_oss_docs.json").read_text(encoding="utf-8"))
    assert len(docs) >= 10
    for doc in docs:
        assert doc["id"].startswith("oss-")
        assert doc["title"]
        assert doc["product"] == "OSS"
        assert doc["category"]
        assert doc["doc_type"] in {"guide", "api_reference", "faq", "troubleshooting", "best_practice"}
        assert doc["url"].startswith("https://")
        assert "alibabacloud.com" in doc["url"] or "aliyun.com" in doc["url"]
        assert doc["summary"]
        assert doc["tags"]
        assert len(doc["sections"]) >= 3
        assert all(section["content"].strip() for section in doc["sections"])


def test_processed_chunks_include_oss_support_sections():
    chunks = [
        json.loads(line)
        for line in (PROJECT_ROOT / "data" / "processed" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(chunks) >= 50
    by_type = Counter(chunk["source_type"] for chunk in chunks)
    assert by_type["oss_document_overview"] >= 10
    assert any(chunk["source_type"] == "oss_troubleshooting" for chunk in chunks)
    assert any(chunk["source_type"] == "oss_auth" for chunk in chunks)
    assert any(chunk["source_type"] == "oss_api" for chunk in chunks)
    for chunk in chunks:
        assert chunk["id"].startswith("oss-")
        assert chunk["text"].strip()
        assert chunk["product"] == "OSS"
        assert chunk["category"]
        assert chunk["url"].startswith("https://")
        assert chunk["source_title"]


def test_processed_indexes_match_oss_domain():
    index = json.loads((PROJECT_ROOT / "data" / "processed" / "retrieval_index.json").read_text(encoding="utf-8"))
    documents = json.loads((PROJECT_ROOT / "data" / "processed" / "documents_index.json").read_text(encoding="utf-8"))
    topics = json.loads((PROJECT_ROOT / "data" / "processed" / "topics_manifest.json").read_text(encoding="utf-8"))
    vector_index = json.loads((PROJECT_ROOT / "data" / "processed" / "vector_index.json").read_text(encoding="utf-8"))
    assert index["product"] == "Alibaba Cloud OSS"
    assert index["retrieval"] == "hybrid_dense_vector_bm25"
    assert index["document_count"] == len(documents)
    assert index["topic_count"] == len(topics)
    assert "enabled" in vector_index
    assert "chunks" in vector_index
    assert documents
    assert topics


def test_processed_chunks_exclude_previous_domain_and_course_materials():
    text = (PROJECT_ROOT / "data" / "processed" / "chunks.jsonl").read_text(encoding="utf-8")
    forbidden_terms = ["CS599", "课程要求", "作业要求", "项目说明", "报告文本"]
    assert not any(term in text for term in forbidden_terms)
    assert "Alibaba Cloud OSS" in (PROJECT_ROOT / "data" / "processed" / "retrieval_index.json").read_text(encoding="utf-8")
