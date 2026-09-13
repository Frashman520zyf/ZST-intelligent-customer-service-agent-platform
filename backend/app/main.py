from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent import SupportAgent
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


knowledge = KnowledgeBase(settings.knowledge_path)
records = UsageRecords(settings.records_path)
llm = DashScopeClient()
agent = SupportAgent(knowledge, records, llm)

app = FastAPI(title="智扫通智能客服 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=settings.model,
        dashscope_configured=llm.configured,
        knowledge_documents=len(knowledge.chunks),
        records=len(records.items),
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await agent.answer(request)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    response = await agent.answer(request)

    async def events() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'type': 'meta', 'conversation_id': response.conversation_id}, ensure_ascii=False)}\n\n"
        for chunk in response.answer.splitlines(keepends=True):
            yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'response': response.model_dump()}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/knowledge/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(query: str = Query(min_length=1, max_length=200)) -> KnowledgeSearchResponse:
    hits = knowledge.search(query)
    return KnowledgeSearchResponse(
        query=query,
        results=[SourceItem(source=item.source, excerpt=item.content[:240], score=item.score) for item in hits],
    )


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
