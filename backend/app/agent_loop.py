"""Closed-loop orchestration for the support agent.

The module is deliberately dependency-light: SQLite and the Python standard
library provide persistence while the existing :class:`SupportAgent` remains
the answer generator.  Mount ``create_agent_loop_router(...)`` from ``main``
to expose the APIs.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from .config import settings
from .loop_schemas import (
    AgentLoopRequest,
    AgentLoopResponse,
    EvaluationCreateRequest,
    EvaluationCase,
    EvaluationMetrics,
    EvaluationResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EventCreateRequest,
    EventResponse,
    IntentResult,
    MemoryItem,
    TicketCreateRequest,
    TicketResponse,
    TicketUpdateRequest,
    ObservabilitySummary,
)
from .schemas import ChatMessage, ChatRequest
from .retrieval import tokenize


def _now() -> str:
    return datetime.now(UTC).isoformat()


class IntentRouter:
    """Fast deterministic intent router used before invoking the LLM."""

    RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
        # Keep high-risk phrases first.  The router is intentionally
        # deterministic, but each match is negation-aware so phrases such as
        # “没有冒烟” and “不需要转人工” do not create false escalations.
        ("safety_incident", ("起火", "着火", "冒烟", "燃烧", "触电", "爆炸", "漏水", "电池鼓包", "危险")),
        ("human_handoff", ("转人工", "人工客服", "人工介入", "投诉", "申诉", "举报", "人工")),
        ("after_sales", ("维修", "售后", "保修", "退货", "退款", "换货", "发票")),
        ("troubleshooting", ("故障", "报错", "异常", "不工作", "无法", "不能", "卡住", "漏扫", "噪音", "回充失败")),
        ("maintenance", ("清洁", "维护", "保养", "耗材", "滤网", "边刷", "主刷", "拖布", "尘盒")),
        ("usage_report", ("报告", "使用记录", "使用情况", "清洁数据", "月度数据")),
        ("product_advice", ("购买", "选购", "型号", "价格", "对比", "推荐")),
    )

    # Chinese negation is usually expressed immediately before the trigger,
    # but can include a short aspect word (for example “没有出现冒烟”).  The
    # bounded window avoids incorrectly suppressing a later independent clause
    # such as “没有冒烟，但是需要维修”。
    _NEGATION_RE = re.compile(
        r"(?:不需要|不必|无需|无须|不用|不要|没有|没|未|无|不|别|不是|并非|暂不)"
        r"[^，。！？；;、,!?]{0,4}$"
    )
    # Conjunctions and contrast markers start a new clause.  They are kept
    # separate from punctuation because Chinese support messages frequently
    # omit commas (for example ``没有冒烟但漏水``).  Without this boundary a
    # negation in the first clause can incorrectly suppress a positive safety
    # or fault signal in the following clause.
    _CLAUSE_BOUNDARY_RE = re.compile(
        r"(?:但是|而是|并且|以及|同时|然而|不过|可是|只是|但|也|而|且)"
    )

    @classmethod
    def _is_negated(cls, text: str, start: int) -> bool:
        prefix = text[max(0, start - 8) : start]
        # Only inspect the clause immediately preceding the trigger.  Looking
        # through a contrast/conjunction marker would make phrases such as
        # ``没有冒烟但漏水`` and ``不是故障而是漏水`` appear wholly negated.
        boundaries = list(cls._CLAUSE_BOUNDARY_RE.finditer(prefix))
        if boundaries:
            prefix = prefix[boundaries[-1].end() :]
        compact = re.sub(r"\s+", "", prefix)
        return bool(cls._NEGATION_RE.search(compact))

    @classmethod
    def _keyword_reasons(cls, text: str, keywords: tuple[str, ...]) -> list[str]:
        reasons: list[str] = []
        for keyword in keywords:
            found = False
            cursor = 0
            while cursor < len(text):
                position = text.find(keyword, cursor)
                if position < 0:
                    break
                # A generic “人工” should not match “人工智能”; explicit
                # handoff phrases (转人工/人工客服) are separate keywords.
                if keyword == "人工" and text[position + len(keyword) :].startswith("智能"):
                    cursor = position + len(keyword)
                    continue
                if not cls._is_negated(text, position):
                    found = True
                    break
                cursor = position + max(1, len(keyword))
            if found:
                reasons.append(keyword)
        return reasons

    def classify(self, message: str) -> IntentResult:
        text = message.strip().lower()
        matches: list[tuple[str, int, list[str]]] = []
        for intent, keywords in self.RULES:
            reasons = self._keyword_reasons(text, keywords)
            if reasons:
                matches.append((intent, len(reasons), reasons))
        if not matches:
            return IntentResult(
                intent="general_support",
                confidence=0.35,
                reasons=["未命中明确意图，交由通用客服处理"],
            )
        priority = {name: index for index, (name, _) in enumerate(self.RULES)}
        # Safety incidents always outrank a simultaneous request for a human
        # agent (e.g. "机器冒烟了，请转人工").  Remaining matches are retained
        # as a route chain so a compound question is not flattened to one label.
        matches.sort(key=lambda item: (0 if item[0] == "safety_incident" else 1, -item[1], priority[item[0]]))
        intent, count, reasons = matches[0]
        chain = [item[0] for item in matches]
        secondary = chain[1:]
        # A single keyword is a useful hint but not certainty.  Multiple
        # independent terms raise confidence without ever reaching 1.0.
        confidence = min(0.98, 0.58 + 0.12 * (count - 1))
        # Explicit handoff/safety phrases are stronger than a generic keyword;
        # this avoids routing ordinary questions containing “客服” to a ticket.
        if intent == "human_handoff" and any(phrase in text for phrase in ("转人工", "人工客服", "人工介入", "投诉", "申诉", "举报")):
            confidence = max(confidence, 0.9)
        entities: dict[str, str] = {}
        model = re.search(
            r"(?:型号|model)\s*(?:是|为)?\s*[:：]?\s*"
            r"([A-Za-z0-9][A-Za-z0-9]*(?:[ _-]+[A-Za-z0-9][A-Za-z0-9]*){0,3})",
            message,
            re.I,
        )
        if model:
            entities["model"] = model.group(1)
        serial = re.search(r"(?:序列号|SN)\s*[:：]?\s*([A-Za-z0-9\-_]+)", message, re.I)
        if serial:
            entities["serial_number"] = serial.group(1)
        month = re.search(r"(20\d{2}[-年]\d{1,2}(?:月)?)", message)
        if month:
            entities["month"] = month.group(1).replace("年", "-").replace("月", "")
        error_code = re.search(r"(?:错误码|报错|error|code)\s*[:：]?\s*([A-Za-z0-9\-_]+)", message, re.I)
        if error_code:
            entities["error_code"] = error_code.group(1)
        area = re.search(r"(\d+(?:\.\d+)?)\s*(?:平米|平方米|㎡)", message)
        if area:
            entities["area_sqm"] = area.group(1)
        if intent == "safety_incident":
            confidence = max(confidence, 0.95)
        return IntentResult(
            intent=intent,
            confidence=confidence,
            entities=entities,
            reasons=reasons,
            secondary_intents=secondary,
            chain=chain,
        )


class AgentLoopStore:
    """SQLite persistence for memories, tickets, events and evaluations."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or (settings.project_root / "data" / "agent_loop.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL, conversation_id TEXT,
                    memory_type TEXT NOT NULL, key TEXT NOT NULL,
                    value TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, memory_type, created_at);
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, conversation_id TEXT,
                    subject TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
                    priority TEXT NOT NULL, status TEXT NOT NULL, assigned_to TEXT,
                    metadata TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status, priority, updated_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                    severity TEXT NOT NULL, message TEXT NOT NULL, user_id TEXT,
                    conversation_id TEXT, context TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                    conversation_id TEXT, question TEXT NOT NULL, answer TEXT NOT NULL,
                    expected TEXT, score REAL NOT NULL, rating INTEGER, feedback TEXT,
                    intent TEXT, created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _decode_memory_value(row: sqlite3.Row) -> Any:
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return row["value"]

    @classmethod
    def _memory_item(cls, row: sqlite3.Row, *, value: Any | None = None) -> MemoryItem:
        decoded = cls._decode_memory_value(row) if value is None else value
        return MemoryItem(
            id=row["id"],
            user_id=row["user_id"],
            conversation_id=row["conversation_id"],
            memory_type=row["memory_type"],
            key=row["key"],
            value=decoded,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def add_memory(self, user_id: str, conversation_id: str | None, memory_type: str, key: str, value: Any) -> MemoryItem:
        """Persist a memory, de-duplicating repeated long-term facts.

        Short-term and episodic entries intentionally remain append-only so a
        transcript/event stream keeps its chronology.  Long-term facts are
        profile state: writing the same ``key``/``value`` repeatedly should
        not grow an unbounded set of identical rows.  A different value for
        the same key is retained and naturally supersedes older values when
        the profile is resolved below.
        """
        created = _now()
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            if memory_type == "long_term":
                # Compare decoded values as well as their JSON representation
                # so rows written by older versions (without sorted keys) are
                # still recognised as duplicates.
                candidates = conn.execute(
                    "SELECT * FROM memories WHERE user_id=? AND memory_type=? AND key=? ORDER BY id DESC",
                    (user_id, memory_type, key),
                ).fetchall()
                for row in candidates:
                    if self._decode_memory_value(row) == value:
                        return self._memory_item(row)
            cur = conn.execute(
                "INSERT INTO memories(user_id, conversation_id, memory_type, key, value, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, conversation_id, memory_type, key, encoded, created),
            )
            row_id = int(cur.lastrowid)
        return MemoryItem(
            id=row_id,
            user_id=user_id,
            conversation_id=conversation_id,
            memory_type=memory_type,
            key=key,
            value=value,
            created_at=datetime.fromisoformat(created),
        )

    def memories(
        self,
        user_id: str,
        memory_type: str | None = None,
        limit: int = 50,
        conversation_id: str | None = None,
    ) -> list[MemoryItem]:
        query = "SELECT * FROM memories WHERE user_id=?"
        params: list[Any] = [user_id]
        if memory_type:
            query += " AND memory_type=?"
            params.append(memory_type)
        if conversation_id:
            query += " AND conversation_id=?"
            params.append(conversation_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._memory_item(row) for row in rows]

    def memory_context(self, user_id: str, conversation_id: str | None) -> tuple[list[ChatMessage], str]:
        """Recall short-term turns plus long-term and episodic profile facts.

        Episodic memories are intentionally summarised rather than injected as
        raw chat turns: this preserves the distinction between an event trail
        and the rolling transcript while still giving the model recent intent
        context across conversations.
        """
        short = self.memories(user_id, "short_term", 16, conversation_id)
        short.reverse()
        messages = [
            ChatMessage(
                role="assistant" if item.key == "assistant_answer" else "user",
                content=str(item.value),
            )
            for item in short
            if item.key in {"user_message", "assistant_answer"}
        ]
        long_term = self.memories(user_id, "long_term", 50)
        stable: dict[str, Any] = {}
        for item in long_term:  # newest row wins for each key
            stable.setdefault(item.key, item.value)
        episodic = self.memories(user_id, "episodic", 12)
        # De-duplicate identical event summaries while preserving newest-first
        # order.  Distinct turns with the same intent remain represented by a
        # bounded count rather than flooding the prompt.
        recent_events: list[str] = []
        seen_events: set[str] = set()
        for item in episodic:
            value = item.value
            if isinstance(value, dict):
                intent_name = value.get("intent")
                confidence = value.get("confidence")
                summary = f"intent={intent_name}" if intent_name else str(value)
                if confidence is not None:
                    summary += f", confidence={confidence}"
            else:
                summary = f"{item.key}={value}"
            if summary not in seen_events:
                seen_events.add(summary)
                recent_events.append(summary)

        sections: list[str] = []
        if stable:
            sections.append("长期记忆：" + "；".join(f"{key}={value}" for key, value in list(stable.items())[:12]))
        if recent_events:
            sections.append("近期事件：" + "；".join(recent_events[:8]))
        # ChatRequest caps memory_context at 4000 characters.  Keep the
        # beginning deterministic (long-term facts first) and avoid a Pydantic
        # validation failure when users have many stored entities.
        profile = "\n".join(sections)[:4000]
        return messages[-16:], profile

    def compact_short_term(self, user_id: str, conversation_id: str, keep: int = 30) -> None:
        """Bound transcript growth while preserving episodic/long-term layers."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM memories WHERE memory_type='short_term' AND user_id=? AND conversation_id=? "
                "AND id NOT IN (SELECT id FROM memories WHERE memory_type='short_term' AND user_id=? "
                "AND conversation_id=? ORDER BY id DESC LIMIT ?)",
                (user_id, conversation_id, user_id, conversation_id, max(2, keep)),
            )

    def create_ticket(self, request: TicketCreateRequest) -> TicketResponse:
        now = _now()
        ticket_id = f"TCK-{uuid4().hex[:10].upper()}"
        metadata = json.dumps(request.metadata, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ticket_id, request.user_id, request.conversation_id, request.subject, request.description, request.category, request.priority, "open", None, metadata, now, now),
            )
        return self.ticket(ticket_id)  # type: ignore[return-value]

    def ticket(self, ticket_id: str) -> TicketResponse | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return self._ticket_row(row) if row else None

    def active_ticket(
        self,
        user_id: str,
        conversation_id: str,
        category: str,
    ) -> TicketResponse | None:
        """Return an unresolved ticket for the same conversation and route."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE user_id=? AND conversation_id=? "
                "AND category=? AND status IN ('open','pending','in_progress') "
                "ORDER BY updated_at DESC LIMIT 1",
                (user_id, conversation_id, category),
            ).fetchone()
        return self._ticket_row(row) if row else None

    @staticmethod
    def _ticket_row(row: sqlite3.Row) -> TicketResponse:
        try:
            metadata = json.loads(row["metadata"])
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        return TicketResponse(id=row["id"], user_id=row["user_id"], conversation_id=row["conversation_id"], subject=row["subject"], description=row["description"], category=row["category"], priority=row["priority"], status=row["status"], assigned_to=row["assigned_to"], metadata=metadata, created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]))

    def list_tickets(self, status: str | None = None, user_id: str | None = None, limit: int = 50) -> list[TicketResponse]:
        query = "SELECT * FROM tickets WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status=?"; params.append(status)
        if user_id:
            query += " AND user_id=?"; params.append(user_id)
        query += " ORDER BY updated_at DESC LIMIT ?"; params.append(max(1, min(limit, 200)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._ticket_row(row) for row in rows]

    def update_ticket(self, ticket_id: str, request: TicketUpdateRequest) -> TicketResponse | None:
        # ``exclude_none=True`` cannot distinguish an omitted field from an
        # explicit JSON ``null``.  ``assigned_to: null`` is meaningful in the
        # UI (it clears the current assignee), so use Pydantic's
        # ``exclude_unset`` tracking and preserve that one nullable update.
        supplied = request.model_dump(exclude_unset=True)
        updates: dict[str, Any] = {
            key: value
            for key, value in supplied.items()
            if key not in {"metadata", "assigned_to"} and value is not None
        }
        if "assigned_to" in supplied:
            updates["assigned_to"] = supplied["assigned_to"]
        if "metadata" in supplied:
            # The database column is NOT NULL; explicit null means reset the
            # metadata object to an empty mapping.
            updates["metadata"] = json.dumps(supplied["metadata"] or {}, ensure_ascii=False)
        if not updates:
            return self.ticket(ticket_id)
        updates["updated_at"] = _now()
        setters = ", ".join(f"{key}=?" for key in updates)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE tickets SET {setters} WHERE id=?", [*updates.values(), ticket_id])
            if cur.rowcount == 0:
                return None
        return self.ticket(ticket_id)

    def add_event(self, request: EventCreateRequest) -> EventResponse:
        created = _now()
        with self._connect() as conn:
            cur = conn.execute("INSERT INTO events(event_type,severity,message,user_id,conversation_id,context,created_at) VALUES (?,?,?,?,?,?,?)", (request.event_type, request.severity, request.message, request.user_id, request.conversation_id, json.dumps(request.context, ensure_ascii=False), created))
            row_id = int(cur.lastrowid)
        return EventResponse(id=row_id, event_type=request.event_type, severity=request.severity, message=request.message, user_id=request.user_id, conversation_id=request.conversation_id, context=request.context, created_at=datetime.fromisoformat(created))

    def events(self, severity: str | None = None, limit: int = 100) -> list[EventResponse]:
        query = "SELECT * FROM events"; params: list[Any] = []
        if severity:
            query += " WHERE severity=?"; params.append(severity)
        query += " ORDER BY id DESC LIMIT ?"; params.append(max(1, min(limit, 500)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            try: context = json.loads(row["context"])
            except (TypeError, json.JSONDecodeError): context = {}
            result.append(EventResponse(id=row["id"], event_type=row["event_type"], severity=row["severity"], message=row["message"], user_id=row["user_id"], conversation_id=row["conversation_id"], context=context, created_at=datetime.fromisoformat(row["created_at"])))
        return result

    def add_evaluation(self, request: EvaluationCreateRequest, intent: str | None = None) -> EvaluationResponse:
        # Explicit user feedback is the strongest signal in this local demo.
        # Automatic heuristics remain available when no star rating is given.
        score = round(request.rating / 5, 3) if request.rating is not None else self.score(
            request.question,
            request.answer,
            request.expected,
        )
        created = _now()
        with self._connect() as conn:
            cur = conn.execute("INSERT INTO evaluations(user_id,conversation_id,question,answer,expected,score,rating,feedback,intent,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (request.user_id, request.conversation_id, request.question, request.answer, request.expected, score, request.rating, request.feedback, intent, created))
            row_id = int(cur.lastrowid)
        return EvaluationResponse(
            id=row_id,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            question=request.question,
            score=score,
            rating=request.rating,
            feedback=request.feedback,
            created_at=datetime.fromisoformat(created),
        )

    @staticmethod
    def score(question: str, answer: str, expected: str | None = None) -> float:
        """Transparent relevance/action/safety baseline for demo evaluation."""
        if not answer.strip():
            return 0.0
        answer_terms = {term for term in tokenize(answer) if len(term) > 1}
        if expected:
            expected_terms = {term for term in tokenize(expected) if len(term) > 1}
            coverage = len(expected_terms & answer_terms) / max(len(expected_terms), 1)
            return round(min(1.0, 0.2 + 0.8 * coverage), 3)

        question_terms = {term for term in tokenize(question) if len(term) > 1}
        relevance = len(question_terms & answer_terms) / max(len(question_terms), 1)
        action_markers = {
            "断电", "停止使用", "检查", "清理", "清洗", "晾干", "更换",
            "重启", "确认", "联系售后", "转人工", "关闭", "打开", "尝试",
        }
        action_score = min(1.0, len(action_markers & answer_terms) / 2)
        length_score = min(1.0, len(answer.strip()) / 160)

        safety_signals = {"起火", "着火", "冒烟", "燃烧", "触电", "爆炸", "漏水", "电池鼓包", "危险"}
        is_safety_question = any(signal in question for signal in safety_signals)
        if is_safety_question:
            safety_actions = {"断电", "停止使用", "远离", "不要充电", "联系售后", "转人工"}
            safety_score = min(1.0, len(safety_actions & answer_terms) / 2)
            score = 0.1 + 0.15 * relevance + 0.25 * action_score + 0.45 * safety_score + 0.05 * length_score
        else:
            score = 0.1 + 0.5 * relevance + 0.25 * action_score + 0.15 * length_score

        # Long, unrelated prose must not outscore a concise actionable answer.
        if relevance == 0 and action_score == 0:
            score = min(score, 0.2)
        return round(min(1.0, score), 3)

    def metrics(self, user_id: str | None = None) -> EvaluationMetrics:
        where = " WHERE user_id=?" if user_id else ""; params = [user_id] if user_id else []
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) count, AVG(score) avg_score, AVG(rating) avg_rating FROM evaluations{where}", params).fetchone()
            intent_rows = conn.execute(f"SELECT intent, AVG(score) avg_score FROM evaluations{where} AND intent IS NOT NULL GROUP BY intent" if where else "SELECT intent, AVG(score) avg_score FROM evaluations WHERE intent IS NOT NULL GROUP BY intent", params if where else []).fetchall()
        return EvaluationMetrics(count=int(row["count"] or 0), average_score=round(float(row["avg_score"] or 0), 3), average_rating=round(float(row["avg_rating"]), 2) if row["avg_rating"] is not None else None, by_intent={item["intent"]: round(float(item["avg_score"] or 0), 3) for item in intent_rows})

    def observability(self) -> dict[str, Any]:
        """Return a compact operational snapshot for the dashboard/health API."""
        with self._connect() as conn:
            event_row = conn.execute(
                "SELECT COUNT(*) total, "
                "SUM(CASE WHEN severity IN ('error','critical') THEN 1 ELSE 0 END) errors, "
                "SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) warnings "
                "FROM events"
            ).fetchone()
            tickets = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE status IN ('open','pending','in_progress')"
            ).fetchone()[0]
            eval_row = conn.execute(
                "SELECT COUNT(*) count, AVG(score) score FROM evaluations"
            ).fetchone()
            latency_row = conn.execute(
                "SELECT AVG(CAST(json_extract(context, '$.latency_ms') AS REAL)) latency, "
                "AVG(CASE WHEN json_extract(context, '$.fallback') IN (1, 'true') THEN 1.0 ELSE 0.0 END) fallback "
                "FROM events WHERE event_type='agent_turn'"
            ).fetchone()
            intents = conn.execute(
                "SELECT COALESCE(json_extract(context, '$.intent'), 'unknown') intent, COUNT(*) count "
                "FROM events WHERE event_type='agent_turn' GROUP BY intent"
            ).fetchall()
        return {
            "events": int(event_row["total"] or 0),
            "errors": int(event_row["errors"] or 0),
            "warnings": int(event_row["warnings"] or 0),
            "open_tickets": int(tickets or 0),
            "evaluations": int(eval_row["count"] or 0),
            "average_score": round(float(eval_row["score"] or 0), 3),
            "average_latency_ms": round(float(latency_row["latency"]), 2) if latency_row["latency"] is not None else None,
            "fallback_rate": round(float(latency_row["fallback"] or 0), 3),
            "intent_distribution": {str(row["intent"]): int(row["count"] or 0) for row in intents},
        }


class AgentLoopService:
    def __init__(self, support_agent: Any | None = None, store: AgentLoopStore | None = None) -> None:
        self.support_agent = support_agent
        self.store = store or AgentLoopStore()
        self.router = IntentRouter()

    @staticmethod
    def default_evaluation_cases() -> list[EvaluationCase]:
        return [
            EvaluationCase(question="主刷被毛发缠住了，应该怎么处理？", expected="断电 清理主刷 毛发"),
            EvaluationCase(question="请给我 2025-02 的使用报告", expected="使用报告 清洁 耗材"),
            EvaluationCase(question="机器冒烟了，马上转人工", expected="停止使用 转人工 工单", user_id="1001"),
            EvaluationCase(question="我准备购买扫拖一体机器人，怎么选？", expected="选购 扫拖一体"),
        ]

    async def run_evaluation(self, request: EvaluationRunRequest) -> EvaluationRunResponse:
        cases = list(request.cases)
        if request.include_default_cases:
            cases = self.default_evaluation_cases() + cases
        # Cap work even if a client sends a large benchmark payload.
        cases = cases[:100]
        results: list[EvaluationResponse] = []
        for case in cases:
            result = await self.handle(
                AgentLoopRequest(
                    message=case.question,
                    user_id=case.user_id,
                    metadata={
                        "evaluation_run": True,
                        **({"expected_answer": case.expected} if case.expected else {}),
                    },
                )
            )
            # The loop already records an evaluation.  Return a lightweight
            # feedback record tied to this run without invoking the model twice.
            score = self.store.score(case.question, result.answer, case.expected)
            results.append(
                EvaluationResponse(
                    id=result.evaluation_id or 0,
                    user_id=case.user_id,
                    conversation_id=result.conversation_id,
                    question=case.question,
                    score=score,
                    created_at=datetime.now(UTC),
                )
            )
        average = round(sum(item.score for item in results) / len(results), 3) if results else 0.0
        return EvaluationRunResponse(
            run_id=str(uuid4()),
            count=len(results),
            average_score=average,
            cases=results,
            metrics=self.store.metrics(),
        )

    async def handle(self, request: AgentLoopRequest) -> AgentLoopResponse:
        started = perf_counter()
        conversation_id = request.conversation_id or str(uuid4())
        trace_id = str(uuid4())
        intent = self.router.classify(request.message)
        if request.intent_hint and request.intent_hint != intent.intent:
            # Keep the deterministic classifier as the source of truth but
            # retain a trusted upstream hint as a secondary route for callers
            # that already performed a first-pass classification.
            intent = intent.model_copy(
                update={
                    "secondary_intents": list(dict.fromkeys([request.intent_hint, *intent.secondary_intents])),
                    "chain": list(dict.fromkeys([intent.intent, request.intent_hint, *intent.secondary_intents])),
                }
            )
        # Recall the previous turn before persisting the current user message;
        # otherwise the current prompt is duplicated in the history sent to the
        # model.  Explicit request history is merged with durable memory and
        # de-duplicated by role/content.
        memory_messages, memory_profile = self.store.memory_context(request.user_id, conversation_id)
        memories: list[MemoryItem] = [self.store.add_memory(request.user_id, conversation_id, "short_term", "user_message", request.message)]
        # Episodic memory captures the outcome of this turn independently of
        # the rolling short-term transcript, making it useful for analytics and
        # future retrieval without leaking the full conversation.
        memories.append(self.store.add_memory(request.user_id, conversation_id, "episodic", "intent", {"intent": intent.intent, "confidence": intent.confidence}))
        for key, value in request.memory_updates.items():
            memories.append(self.store.add_memory(request.user_id, conversation_id, "long_term", key, value))
        # Entity extraction is an inexpensive way to turn useful device facts
        # into stable long-term memory.  Newer values are appended and the
        # profile resolver gives the newest record precedence.
        for key, value in intent.entities.items():
            memories.append(self.store.add_memory(request.user_id, conversation_id, "long_term", key, value))
        answer = "已收到你的问题。请提供设备型号、故障现象和报错信息，我会继续帮你排查。"
        sources = []
        report = None
        model = None
        fallback = True
        retrieval: dict[str, Any] = {}
        if self.support_agent is not None:
            try:
                history = list(memory_messages)
                for item in request.history:
                    if not any(old.role == item.role and old.content == item.content for old in history):
                        history.append(item)
                history = history[-16:]
                result = await self.support_agent.answer(
                    ChatRequest(
                        message=request.message,
                        user_id=request.user_id,
                        conversation_id=conversation_id,
                        history=history,
                        memory_context=request.memory_context or memory_profile,
                        intent_hint=intent.intent,
                    )
                )
                answer = result.answer
                sources = result.sources
                report = result.report
                model = result.model
                fallback = result.fallback
                retrieval = {
                    "sources": len(sources),
                    "citations": [item.citation for item in sources if item.citation],
                }
                retrieval.update(getattr(result, "retrieval", {}) or {})
            except Exception as exc:  # keep the loop available when the model is down
                self.store.add_event(
                    EventCreateRequest(
                        event_type="agent_error",
                        severity="error",
                        message="Agent request failed; fallback response returned",
                        user_id=request.user_id,
                        conversation_id=conversation_id,
                        context={"trace_id": trace_id, "error_type": type(exc).__name__},
                    )
                )
        else:
            if intent.intent == "usage_report":
                answer = "我可以帮你生成使用报告，请确认需要查询的月份。"
            elif intent.intent in {"human_handoff", "safety_incident"}:
                answer = "这个问题需要人工售后尽快介入，我正在为你创建工单。"
        # Escalation follows the positive, negation-aware intent result.  A
        # raw substring check would incorrectly open a ticket for messages
        # such as “没有冒烟，也不需要转人工”。
        escalation = intent.intent in {"human_handoff", "safety_incident"} or any(
            route in {"human_handoff", "safety_incident"} for route in intent.secondary_intents
        )
        ticket_id: str | None = None
        evaluation_run = request.metadata.get("evaluation_run") is True
        if escalation and not evaluation_run:
            priority = "urgent" if intent.intent == "safety_incident" else "high"
            category = "safety" if intent.intent == "safety_incident" else "after_sales"
            ticket = self.store.active_ticket(request.user_id, conversation_id, category)
            if ticket is None:
                ticket = self.store.create_ticket(TicketCreateRequest(user_id=request.user_id, conversation_id=conversation_id, subject=f"{intent.intent}｜{request.message[:60]}", description=request.message, category=category, priority=priority, metadata={"trace_id": trace_id, "intent": intent.intent}))
                self.store.add_event(EventCreateRequest(event_type="ticket_created", severity="critical" if priority == "urgent" else "warning", message=f"自动创建售后工单 {ticket.id}", user_id=request.user_id, conversation_id=conversation_id, context={"ticket_id": ticket.id, "intent": intent.intent}))
            ticket_id = ticket.id
        expected = request.metadata.get("expected_answer")
        if expected is not None and not isinstance(expected, str):
            expected = str(expected)
        evaluation = self.store.add_evaluation(EvaluationCreateRequest(user_id=request.user_id, conversation_id=conversation_id, question=request.message, answer=answer, expected=expected), intent=intent.intent)
        memories.append(self.store.add_memory(request.user_id, conversation_id, "short_term", "assistant_answer", answer[:4000]))
        latency_ms = (perf_counter() - started) * 1000
        self.store.add_event(
            EventCreateRequest(
                event_type="agent_turn",
                severity="warning" if fallback else "info",
                message="agent turn completed",
                user_id=request.user_id,
                conversation_id=conversation_id,
                context={
                    "trace_id": trace_id,
                    "intent": intent.intent,
                    "confidence": intent.confidence,
                    "latency_ms": round(latency_ms, 2),
                    "fallback": fallback,
                    "escalation": escalation,
                    "secondary_intents": intent.secondary_intents,
                    "entities": intent.entities,
                    "retrieval": retrieval,
                    "ticket_id": ticket_id,
                    "evaluation_run": evaluation_run,
                },
            )
        )
        self.store.compact_short_term(request.user_id, conversation_id)
        return AgentLoopResponse(
            trace_id=trace_id,
            conversation_id=conversation_id,
            user_id=request.user_id,
            intent=intent,
            answer=answer,
            escalation_required=escalation,
            ticket_id=ticket_id,
            memories=memories,
            evaluation_id=evaluation.id,
            sources=sources,
            report=report,
            model=model,
            fallback=fallback,
            retrieval=retrieval,
            latency_ms=round(latency_ms, 2),
        )


def create_agent_loop_router(service: AgentLoopService | None = None) -> APIRouter:
    service = service or AgentLoopService()
    router = APIRouter(prefix="/api", tags=["agent-loop"])

    @router.post("/agent/intent", response_model=IntentResult)
    async def classify_intent(request: AgentLoopRequest) -> IntentResult:
        return service.router.classify(request.message)

    @router.post("/agent/loop", response_model=AgentLoopResponse)
    async def agent_loop(request: AgentLoopRequest) -> AgentLoopResponse:
        return await service.handle(request)

    @router.get("/agent/memory/{user_id}", response_model=list[MemoryItem])
    async def user_memories(
        user_id: str,
        memory_type: str | None = Query(default=None),
        conversation_id: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[MemoryItem]:
        return service.store.memories(user_id, memory_type, limit, conversation_id)

    @router.post("/tickets", response_model=TicketResponse, status_code=201)
    async def create_ticket(request: TicketCreateRequest) -> TicketResponse:
        ticket = service.store.create_ticket(request)
        service.store.add_event(
            EventCreateRequest(
                event_type="ticket_created",
                severity="critical" if ticket.priority == "urgent" else "info",
                message=f"售后工单 {ticket.id} 已创建",
                user_id=ticket.user_id,
                conversation_id=ticket.conversation_id,
                context={"ticket_id": ticket.id, "category": ticket.category, "priority": ticket.priority},
            )
        )
        return ticket

    @router.get("/tickets", response_model=list[TicketResponse])
    async def list_tickets(status: str | None = None, user_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)) -> list[TicketResponse]:
        return service.store.list_tickets(status=status, user_id=user_id, limit=limit)

    @router.get("/tickets/{ticket_id}", response_model=TicketResponse)
    async def get_ticket(ticket_id: str) -> TicketResponse:
        ticket = service.store.ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在")
        return ticket

    @router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
    async def update_ticket(ticket_id: str, request: TicketUpdateRequest) -> TicketResponse:
        before = service.store.ticket(ticket_id)
        ticket = service.store.update_ticket(ticket_id, request)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在")
        # Keep explicit ``assigned_to: null`` in the audit payload so the
        # monitoring timeline shows that an assignee was cleared.
        changed = request.model_dump(exclude_unset=True)
        if changed:
            # Status/assignee changes are part of the operational audit trail,
            # so the monitoring workspace can explain who moved a ticket and
            # from which state.  Direct store callers remain lightweight, while
            # API mutations are always observable.
            service.store.add_event(
                EventCreateRequest(
                    event_type="ticket_updated",
                    severity="info" if request.status not in {"resolved", "closed"} else "warning",
                    message=f"售后工单 {ticket.id} 已更新",
                    user_id=ticket.user_id,
                    conversation_id=ticket.conversation_id,
                    context={
                        "ticket_id": ticket.id,
                        "before_status": before.status if before else None,
                        "after_status": ticket.status,
                        "changes": changed,
                    },
                )
            )
        return ticket

    @router.post("/events", response_model=EventResponse, status_code=201)
    async def create_event(request: EventCreateRequest) -> EventResponse:
        return service.store.add_event(request)

    @router.get("/events", response_model=list[EventResponse])
    async def list_events(severity: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> list[EventResponse]:
        return service.store.events(severity=severity, limit=limit)

    @router.post("/evaluations", response_model=EvaluationResponse, status_code=201)
    async def create_evaluation(request: EvaluationCreateRequest) -> EvaluationResponse:
        response = service.store.add_evaluation(request)
        service.store.add_event(
            EventCreateRequest(
                event_type="evaluation_recorded",
                severity="info",
                message="已记录一条自动评测结果",
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                context={"evaluation_id": response.id, "score": response.score},
            )
        )
        return response

    @router.get("/evaluations/metrics", response_model=EvaluationMetrics)
    async def evaluation_metrics(user_id: str | None = None) -> EvaluationMetrics:
        return service.store.metrics(user_id=user_id)

    @router.post("/evaluations/run", response_model=EvaluationRunResponse)
    async def run_evaluations(request: EvaluationRunRequest) -> EvaluationRunResponse:
        return await service.run_evaluation(request)

    @router.post("/feedback", response_model=EvaluationResponse, status_code=201)
    async def submit_feedback(request: EvaluationCreateRequest) -> EvaluationResponse:
        """User feedback is stored as an evaluation and enters the same loop."""
        response = service.store.add_evaluation(request)
        service.store.add_event(
            EventCreateRequest(
                event_type="feedback_received",
                severity="info" if (request.rating or 0) >= 3 else "warning",
                message="客服回答收到用户反馈",
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                context={"evaluation_id": response.id, "rating": request.rating},
            )
        )
        return response

    @router.get("/monitoring/overview", response_model=ObservabilitySummary)
    async def monitoring_overview() -> ObservabilitySummary:
        values = service.store.observability()
        return ObservabilitySummary(generated_at=datetime.now(UTC), **values)

    @router.get("/monitoring/events", response_model=list[EventResponse])
    async def monitoring_events(severity: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> list[EventResponse]:
        return service.store.events(severity=severity, limit=limit)

    return router


# A ready-to-mount router for applications that don't need to inject SupportAgent.
router = create_agent_loop_router()
