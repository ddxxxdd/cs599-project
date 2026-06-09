"""Shared request, response, and support knowledge schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Intent = Literal[
    "knowledge",
    "doc_lookup",
    "api_reference",
    "permission",
    "troubleshooting",
    "cost",
    "smalltalk",
]


class SupportSection(BaseModel):
    heading: str
    kind: Literal["overview", "howto", "auth", "api", "troubleshooting", "faq", "cost"]
    content: str
    tags: list[str] = Field(default_factory=list)


class SupportDocument(BaseModel):
    id: str
    title: str
    product: str = "OSS"
    category: str
    doc_type: Literal["guide", "api_reference", "faq", "troubleshooting", "best_practice"]
    url: str
    source_title: str = "阿里云 OSS 官方文档"
    tags: list[str] = Field(default_factory=list)
    related_apis: list[str] = Field(default_factory=list)
    common_errors: list[str] = Field(default_factory=list)
    summary: str
    sections: list[SupportSection]


class KnowledgeChunk(BaseModel):
    id: str
    title: str
    source_title: str
    url: str
    source_type: str
    tags: list[str] = Field(default_factory=list)
    text: str
    product: str = "OSS"
    category: str = ""
    doc_type: str = ""
    section: str = ""


class Citation(BaseModel):
    chunk_id: str
    title: str
    source_title: str
    url: str
    snippet: str = ""
    score: float = 0.0
    product: str = "OSS"
    category: str = ""
    doc_type: str = ""
    section: str = ""


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: str | None = None


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    question: str
    answer: str
    intent: Intent
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class LookupRequest(BaseModel):
    query: str
