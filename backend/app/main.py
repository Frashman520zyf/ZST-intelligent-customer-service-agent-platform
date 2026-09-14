from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent import SupportAgent
from .agent_loop import AgentLoopService, create_agent_loop_router
from .config import settings
from .knowledge import KnowledgeBase
from .llm import DashScopeClient
from .records import UsageRecords
from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    KnowledgeSearchResponse,
    SourceItem,
)


# Keep generated index artifacts at the project level (outside the source
# documents) so data/ remains portable and the ignored runtime state is easy to
# inspect or clear independently.
knowledge = KnowledgeBase(settings.knowledge_path, index_dir=settings.retrieval_index_path)
records = UsageRecords(settings.records_path)
llm = DashScopeClient()
agent = SupportAgent(knowledge, records, llm)
loop_service = AgentLoopService(support_agent=agent)

app = FastAPI(title="智扫通智能客服 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    # Browsers reject credentialed wildcard CORS. The demo has no login or
    # cookies, but this keeps custom ALLOWED_ORIGINS="*" configurations valid.
    allow_credentials="*" not in settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_agent_loop_router(loop_service))


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    retrieval = knowledge.stats()
    return HealthResponse(
        status="ok",
        model=settings.model,
        dashscope_configured=llm.configured,
        knowledge_documents=int(retrieval.get("files", 0)),
        knowledge_chunks=int(retrieval.get("chunks", 0)),
        records=len(records.items),
        retrieval=retrieval,
        loop_db=loop_service.store.path.name,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    # Route the legacy chat contract through the same closed loop used by the
    # operations dashboard.  This preserves the original response shape while
    # ensuring memory, escalation, monitoring and automatic evaluation are not
    # bypassed by older clients.
    from .loop_schemas import AgentLoopRequest

    result = await loop_service.handle(
        AgentLoopRequest(
            message=request.message,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            history=request.history,
            memory_context=request.memory_context,
            intent_hint=request.intent_hint,
        )
    )
    return ChatResponse(
        answer=result.answer,
        conversation_id=result.conversation_id,
        intent="report" if result.intent.intent == "usage_report" else "support",
        sources=result.sources,
        report=result.report,
        model=result.model or settings.model,
        fallback=result.fallback,
        trace_id=result.trace_id,
        intent_confidence=result.intent.confidence,
        escalation_required=result.escalation_required,
        ticket_id=result.ticket_id,
        latency_ms=result.latency_ms,
        retrieval=result.retrieval,
    )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    response = await chat(request)

    async def events() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'type': 'meta', 'conversation_id': response.conversation_id, 'trace_id': response.trace_id, 'intent': response.intent, 'ticket_id': response.ticket_id}, ensure_ascii=False)}\n\n"
        for chunk in response.answer.splitlines(keepends=True):
            yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'response': response.model_dump()}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/knowledge/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(query: str = Query(min_length=1, max_length=200)) -> KnowledgeSearchResponse:
    hits = await asyncio.to_thread(knowledge.search, query)
    return KnowledgeSearchResponse(
        query=query,
        results=[
            SourceItem(
                source=item.source,
                excerpt=item.content[:240],
                score=item.score,
                citation=item.citation,
                page=(item.metadata or {}).get("page") if item.metadata else None,
                chunk_id=item.chunk_id,
                metadata=item.metadata or {},
            )
            for item in hits
        ],
        total=len(hits),
        strategy="hybrid_tfidf_keyword_vector",
        index=knowledge.stats(),
    )


@app.get("/api/knowledge/index")
async def knowledge_index_status() -> dict[str, object]:
    return knowledge.stats()


@app.get("/api/rag/search")
async def rag_search(
    query: str = Query(min_length=1, max_length=4000),
    top_k: int = Query(default=5, ge=1, le=20),
    max_chars: int = Query(default=6000, ge=500, le=20000),
    diversify_by_source: bool = Query(default=True),
    source: str | None = Query(default=None, max_length=500),
) -> dict[str, object]:
    """Run the auditable hybrid RAG tool.

    This endpoint is intentionally read-only and shares the exact in-process
    index used by ``/api/chat``.  The response includes bounded prompt context,
    score components, citations and retrieval latency so the demo dashboard can
    inspect why a chunk was selected.
    """

    result = await asyncio.to_thread(
        knowledge.rag_search,
        query,
        top_k=top_k,
        max_chars=max_chars,
        source=source,
        diversify_by_source=diversify_by_source,
    )
    return result.as_dict()


@app.post("/api/knowledge/rebuild")
async def knowledge_rebuild(force: bool = Query(default=True)) -> dict[str, object]:
    return await asyncio.to_thread(knowledge.rebuild, force=force)


@app.get("/api/reports/{user_id}")
async def latest_report(user_id: str) -> dict[str, object]:
    report = records.report(user_id)
    if not report:
        raise HTTPException(status_code=404, detail="没有找到该用户的使用记录")
    return report


@app.get("/api/reports/{user_id}/{month}")
async def monthly_report(user_id: str, month: str) -> dict[str, object]:
    report = records.report(user_id, month)
    if not report:
        raise HTTPException(status_code=404, detail="没有找到该用户对应月份的使用记录")
    return report
