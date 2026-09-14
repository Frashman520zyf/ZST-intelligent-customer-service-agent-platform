"""Pydantic contracts for the agent closed-loop APIs.

These models intentionally live in a separate module from ``schemas.py`` so the
new agent orchestration APIs can evolve without changing the existing chat
contract consumed by the frontend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .schemas import ChatMessage, SourceItem


class IntentResult(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    entities: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    secondary_intents: list[str] = Field(default_factory=list)
    chain: list[str] = Field(default_factory=list)


class AgentLoopRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="1001", pattern=r"^\d+$")
    conversation_id: str | None = Field(default=None, max_length=120)
    # Optional explicit profile updates (for example model/serial number).
    memory_updates: dict[str, str] = Field(default_factory=dict, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)
    # Optional prompt context supplied by trusted callers of the legacy chat
    # contract.  Durable memory is still recalled automatically.
    memory_context: str | None = Field(default=None, max_length=4000)
    intent_hint: str | None = Field(default=None, max_length=80)


class MemoryItem(BaseModel):
    id: int
    user_id: str
    conversation_id: str | None = None
    memory_type: Literal["short_term", "long_term", "episodic"]
    key: str
    value: Any
    created_at: datetime


class AgentLoopResponse(BaseModel):
    trace_id: str
    conversation_id: str
    user_id: str
    intent: IntentResult
    answer: str
    escalation_required: bool = False
    ticket_id: str | None = None
    memories: list[MemoryItem] = Field(default_factory=list)
    evaluation_id: int | None = None
    sources: list[SourceItem] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    model: str | None = None
    fallback: bool = False
    retrieval: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None


TicketPriority = Literal["low", "normal", "high", "urgent"]
TicketStatus = Literal["open", "pending", "in_progress", "resolved", "closed"]


class TicketCreateRequest(BaseModel):
    user_id: str = Field(default="1001", pattern=r"^\d+$")
    conversation_id: str | None = Field(default=None, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    category: str = Field(default="after_sales", max_length=80)
    priority: TicketPriority = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)


class TicketUpdateRequest(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] | None = Field(default=None, max_length=50)


class TicketResponse(BaseModel):
    id: str
    user_id: str
    conversation_id: str | None = None
    subject: str
    description: str
    category: str
    priority: TicketPriority
    status: TicketStatus
    assigned_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class EventCreateRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    severity: Literal["info", "warning", "error", "critical"] = "info"
    message: str = Field(min_length=1, max_length=5000)
    user_id: str | None = Field(default=None, pattern=r"^\d+$")
    conversation_id: str | None = Field(default=None, max_length=120)
    context: dict[str, Any] = Field(default_factory=dict, max_length=100)


class EventResponse(BaseModel):
    id: int
    event_type: str
    severity: str
    message: str
    user_id: str | None = None
    conversation_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EvaluationCreateRequest(BaseModel):
    user_id: str = Field(default="1001", pattern=r"^\d+$")
    conversation_id: str | None = Field(default=None, max_length=120)
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=12000)
    expected: str | None = Field(default=None, max_length=12000)
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=5000)


class EvaluationResponse(BaseModel):
    id: int
    user_id: str
    conversation_id: str | None = None
    # Included for benchmark/result screens; optional to keep the feedback API
    # compatible with clients that only consume the score and rating.
    question: str | None = None
    score: float = Field(ge=0, le=1)
    rating: int | None = None
    feedback: str | None = None
    created_at: datetime


class EvaluationMetrics(BaseModel):
    count: int
    average_score: float
    average_rating: float | None = None
    by_intent: dict[str, float] = Field(default_factory=dict)


class EvaluationCase(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    expected: str | None = Field(default=None, max_length=12000)
    user_id: str = Field(default="1001", pattern=r"^\d+$")


class EvaluationRunRequest(BaseModel):
    cases: list[EvaluationCase] = Field(default_factory=list, max_length=100)
    # The built-in set is deliberately small and transparent so the demo can
    # run without a benchmark service or hidden data.
    include_default_cases: bool = True


class EvaluationRunResponse(BaseModel):
    run_id: str
    count: int
    average_score: float
    cases: list[EvaluationResponse] = Field(default_factory=list)
    metrics: EvaluationMetrics


class ObservabilitySummary(BaseModel):
    generated_at: datetime
    events: int
    errors: int
    warnings: int
    open_tickets: int
    evaluations: int
    average_score: float
    average_latency_ms: float | None = None
    fallback_rate: float = 0.0
    intent_distribution: dict[str, int] = Field(default_factory=dict)
