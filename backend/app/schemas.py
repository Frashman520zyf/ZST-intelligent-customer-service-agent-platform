from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="1001", pattern=r"^\d+$")
    conversation_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)


class SourceItem(BaseModel):
    source: str
    excerpt: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    intent: Literal["support", "report"]
    sources: list[SourceItem] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    model: str
    fallback: bool = False


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[SourceItem]


class HealthResponse(BaseModel):
    status: str
    model: str
    dashscope_configured: bool
    knowledge_documents: int
    records: int
