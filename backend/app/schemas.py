from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="1001", pattern=r"^\d+$")
    conversation_id: str | None = Field(default=None, max_length=120)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)
    memory_context: str | None = Field(default=None, max_length=4000)
    intent_hint: str | None = Field(default=None, max_length=80)


class SourceItem(BaseModel):
    source: str
    excerpt: str
    score: float
    citation: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    intent: Literal["support", "report"]
    sources: list[SourceItem] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    model: str
    fallback: bool = False
    trace_id: str | None = None
    intent_confidence: float | None = Field(default=None, ge=0, le=1)
    escalation_required: bool = False
    ticket_id: str | None = None
    latency_ms: float | None = None
    # Auditable retrieval/tool trace.  Kept optional so older clients can
    # continue deserializing the response without knowing the new fields.
    retrieval: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[SourceItem]
    total: int = 0
    strategy: str = "hybrid"
    index: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    model: str
    dashscope_configured: bool
    knowledge_documents: int
    knowledge_chunks: int = 0
    records: int
    retrieval: dict[str, Any] = Field(default_factory=dict)
    loop_db: str | None = None
