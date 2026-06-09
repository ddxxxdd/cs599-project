"""Domain tools used by the Aliyun OSS support Agent."""

from __future__ import annotations

import re

from .config import get_logger, get_settings
from .data_loader import load_json
from .schemas import SupportDocument


logger = get_logger(__name__)
GENERIC_TERMS = {"oss", "对象存储", "guide", "api_reference", "faq", "best_practice"}


class OssSupportTools:
    def __init__(self) -> None:
        settings = get_settings()
        self.documents = [SupportDocument.model_validate(row) for row in list(load_json(settings.documents_path))]
        logger.info("oss_support_docs_loaded count=%s path=%s", len(self.documents), settings.documents_path)
        self.by_id = {doc.id: doc for doc in self.documents}
        self.by_api: dict[str, list[SupportDocument]] = {}
        self.by_term: dict[str, SupportDocument] = {}
        for doc in self.documents:
            for term in [doc.id, doc.title, doc.category, *doc.tags, *doc.related_apis, *doc.common_errors]:
                key = term.lower().strip()
                if key:
                    self.by_term[key] = doc
            for api in doc.related_apis:
                self.by_api.setdefault(api.lower(), []).append(doc)

    def find_documents_in_text(self, text: str) -> list[SupportDocument]:
        lowered = text.lower()
        candidates: list[tuple[int, int, SupportDocument]] = []
        for term, doc in self.by_term.items():
            if len(term) < 2 or term in GENERIC_TERMS:
                continue
            start = lowered.find(term)
            while start >= 0:
                candidates.append((start, start + len(term), doc))
                start = lowered.find(term, start + 1)
        selected: list[tuple[int, int, SupportDocument]] = []
        for start, end, doc in sorted(candidates, key=lambda item: (-(item[1] - item[0]), item[0])):
            if any(start < used_end and end > used_start for used_start, used_end, _used_doc in selected):
                continue
            selected.append((start, end, doc))

        matches: list[SupportDocument] = []
        for _start, _end, doc in sorted(selected, key=lambda item: item[0]):
            if doc not in matches:
                matches.append(doc)
        return matches

    def lookup_document(self, query: str) -> dict[str, object]:
        logger.info("tool_doc_lookup query=%s", query)
        key = query.lower().strip()
        doc = self.by_id.get(key) or self.by_term.get(key)
        if not doc:
            matches = self.find_documents_in_text(query)
            doc = matches[0] if matches else None
        if not doc:
            return {"found": False, "message": f"未找到 OSS 文档：{query}"}
        return {"found": True, "document": doc.model_dump()}

    def lookup_api(self, query: str, limit: int = 5) -> dict[str, object]:
        logger.info("tool_api_lookup query=%s limit=%s", query, limit)
        lowered = query.lower()
        hits: list[SupportDocument] = []
        api_pattern = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Bucket|Object|Multipart|Lifecycle|Policy|Cors|Website|Logging|Versioning|Encryption)\b")
        api_terms = [term.lower() for term in api_pattern.findall(query)]
        for api in api_terms:
            hits.extend(self.by_api.get(api, []))
        if not hits:
            for doc in self.documents:
                if doc.doc_type == "api_reference" or any(api.lower() in lowered for api in doc.related_apis):
                    hits.append(doc)
        return {"matches": [doc.model_dump() for doc in self._dedupe(hits)[:limit]], "count": len(self._dedupe(hits))}

    def filter_by_topic(self, query: str, limit: int = 6) -> dict[str, object]:
        logger.info("tool_topic_filter query=%s limit=%s", query, limit)
        lowered = query.lower()
        hits: list[SupportDocument] = []
        for doc in self.documents:
            haystack = " ".join(
                [
                    doc.title,
                    doc.category,
                    doc.summary,
                    " ".join(doc.tags),
                    " ".join(doc.related_apis),
                    " ".join(doc.common_errors),
                    " ".join(section.heading + " " + section.content + " " + " ".join(section.tags) for section in doc.sections),
                ]
            ).lower()
            if any(token in haystack for token in self._tokens(lowered)):
                hits.append(doc)
        return {"matches": [doc.model_dump() for doc in self._dedupe(hits)[:limit]], "count": len(self._dedupe(hits))}

    def troubleshoot(self, query: str, limit: int = 5) -> dict[str, object]:
        logger.info("tool_troubleshoot query=%s limit=%s", query, limit)
        lowered = query.lower()
        hits = [doc for doc in self.documents if any(error.lower() in lowered for error in doc.common_errors)]
        if hits:
            return {"matches": [doc.model_dump() for doc in self._dedupe(hits)[:limit]], "count": len(self._dedupe(hits))}
        hits = []
        for doc in self.documents:
            error_text = " ".join(
                [
                    *doc.common_errors,
                    doc.title,
                    doc.summary,
                    " ".join(doc.tags),
                    " ".join(section.heading + " " + section.content + " " + " ".join(section.tags) for section in doc.sections),
                ]
            ).lower()
            if any(term in error_text for term in self._tokens(lowered) if term not in GENERIC_TERMS):
                hits.append(doc)
        if not hits:
            hits = [doc for doc in self.documents if doc.doc_type == "troubleshooting"]
        return {"matches": [doc.model_dump() for doc in self._dedupe(hits)[:limit]], "count": len(self._dedupe(hits))}

    def permission_guides(self, query: str, limit: int = 5) -> dict[str, object]:
        logger.info("tool_permission_guides query=%s limit=%s", query, limit)
        hits = [
            doc
            for doc in self.documents
            if doc.category in {"权限控制", "安全与访问", "安全与合规"}
            or any(term in " ".join(doc.tags) for term in ("RAM", "STS", "Policy", "权限", "加密"))
        ]
        focused = [doc for doc in hits if any(token in (doc.title + doc.summary + " ".join(doc.tags)).lower() for token in self._tokens(query.lower()))]
        docs = focused or hits
        return {"matches": [doc.model_dump() for doc in self._dedupe(docs)[:limit]], "count": len(self._dedupe(docs))}

    def _tokens(self, text: str) -> list[str]:
        raw_tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", text)
        domain_terms = [
            "oss",
            "bucket",
            "object",
            "ram",
            "sts",
            "policy",
            "accessdenied",
            "signaturedoesnotmatch",
            "nosuchkey",
            "nosuchbucket",
            "cors",
            "referer",
            "生命周期",
            "分片",
            "加密",
            "权限",
            "签名",
            "静态网站",
            "临时凭证",
            "错误码",
        ]
        tokens = [token.lower() for token in raw_tokens if len(token.strip()) >= 2]
        tokens.extend(term for term in domain_terms if term in text)
        return tokens

    def _dedupe(self, docs: list[SupportDocument]) -> list[SupportDocument]:
        seen: set[str] = set()
        result: list[SupportDocument] = []
        for doc in docs:
            if doc.id in seen:
                continue
            seen.add(doc.id)
            result.append(doc)
        return result


OSS_TOOLS = OssSupportTools()
