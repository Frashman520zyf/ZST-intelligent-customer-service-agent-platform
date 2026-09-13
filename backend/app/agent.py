from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

from .config import settings
from .knowledge import KnowledgeBase, KnowledgeHit
from .llm import DashScopeClient
from .records import UsageRecords
from .schemas import ChatRequest, ChatResponse, SourceItem


SYSTEM_PROMPT = """你是智扫通的专业智能客服，服务对象是扫地机器人和扫拖一体机器人用户。
回答必须使用中文，基于给定知识资料和用户数据，不编造设备型号、政策或维修承诺。
先直接给出结论，再用简洁条目说明操作步骤、注意事项和需要联系售后的情况。
如果资料不足，明确说明需要补充的型号、故障现象或时间，不要虚构答案。"""


def _month_from_message(message: str, available: list[str]) -> str | None:
    match = re.search(r"(20\d{2}-\d{2})", message)
    if match and match.group(1) in available:
        return match.group(1)
    month_match = re.search(r"(\d{1,2})月", message)
    if month_match:
        suffix = f"-{int(month_match.group(1)):02d}"
        for month in available:
            if month.endswith(suffix):
                return month
    return available[0] if available else f"{datetime.now():%Y-%m}"


def _is_report(message: str) -> bool:
    return bool(re.search(r"报告|使用记录|使用情况|清洁数据|月度数据|保养建议", message))


def _source_items(hits: list[KnowledgeHit]) -> list[SourceItem]:
    return [SourceItem(source=hit.source, excerpt=hit.content[:180], score=hit.score) for hit in hits]


class SupportAgent:
    def __init__(self, knowledge: KnowledgeBase, records: UsageRecords, llm: DashScopeClient) -> None:
        self.knowledge = knowledge
        self.records = records
        self.llm = llm

    async def answer(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or str(uuid4())
        report = None
        intent = "report" if _is_report(request.message) else "support"
        context = ""
        hits: list[KnowledgeHit] = []
        if intent == "report":
            months = self.records.months(request.user_id)
            month = _month_from_message(request.message, months)
            report = self.records.report(request.user_id, month)
            context = str(report or "没有找到该用户对应月份的使用记录")
        else:
            context, hits = self.knowledge.context(request.message)

        history = [{"role": item.role, "content": item.content} for item in request.history[-12:]]
        user_content = f"用户问题：{request.message}\n\n参考上下文：\n{context or '暂无匹配资料'}"
        answer = await self.llm.complete(
            [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": user_content}]
        )
        fallback = answer is None
        if answer is None:
            answer = self._fallback(request.message, report, hits)
        return ChatResponse(
            answer=answer,
            conversation_id=conversation_id,
            intent=intent,
            sources=_source_items(hits),
            report=report,
            model=settings.model,
            fallback=fallback,
        )

    @staticmethod
    def _fallback(message: str, report: dict[str, object] | None, hits: list[KnowledgeHit]) -> str:
        if report:
            return (
                f"### {report['title']}\n\n"
                f"**记录月份**：{report['month']}  \n**用户画像**：{report['profile']}\n\n"
                f"**清洁表现**\n{report['efficiency']}\n\n"
                f"**耗材状态**\n{report['consumables']}\n\n"
                f"**同类对比**：{report['comparison']}\n\n"
                "**建议**：按耗材剩余寿命安排更换；若出现持续漏扫、异常噪音或回充失败，请提供设备型号和故障视频，以便售后进一步判断。"
            )
        if hits:
            return f"根据知识库资料，与你的问题最相关的是：\n\n{hits[0].content[:700]}\n\n如需更准确的排查，请补充设备型号、故障提示和发生频率。"
        return "我暂时没有检索到足够资料。请补充扫地机器人型号、具体故障现象，以及是否伴随报错提示。"
