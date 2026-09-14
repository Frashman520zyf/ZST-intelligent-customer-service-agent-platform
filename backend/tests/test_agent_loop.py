from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.app.agent_loop import AgentLoopService, AgentLoopStore, IntentRouter
from backend.app.loop_schemas import (
    AgentLoopRequest,
    EvaluationRunRequest,
    TicketCreateRequest,
    TicketUpdateRequest,
)


class AgentLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "agent-loop.sqlite3"
        self.store = AgentLoopStore(self.db)

    def tearDown(self) -> None:
        # This also verifies that every store operation closes its SQLite
        # connection on Windows, where open database handles block cleanup.
        self.temp_dir.cleanup()

    def test_intent_router_extracts_model(self) -> None:
        result = IntentRouter().classify("型号 S10 无法回充")
        self.assertEqual(result.intent, "troubleshooting")
        self.assertEqual(result.entities["model"], "S10")

    def test_intent_router_handles_compound_negation(self) -> None:
        router = IntentRouter()
        result = router.classify("没有冒烟，也不需要转人工，但机器故障、噪音很大需要维修")
        self.assertEqual(result.intent, "troubleshooting")
        self.assertIn("after_sales", result.secondary_intents)
        self.assertNotIn("safety_incident", result.chain)
        self.assertNotIn("human_handoff", result.chain)

    def test_intent_router_resets_negation_at_clause_boundaries(self) -> None:
        router = IntentRouter()
        # Chinese users often omit punctuation before a contrast/conjunction;
        # a positive signal in the next clause must still be routable.
        cases = {
            "没有冒烟但漏水": "safety_incident",
            "没有冒烟但是漏水": "safety_incident",
            "不是故障而是漏水": "safety_incident",
            "没有故障并且噪音很大": "troubleshooting",
            "没有故障同时噪音很大": "troubleshooting",
            "没有冒烟也漏水": "safety_incident",
            "没有冒烟而且漏水": "safety_incident",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                result = router.classify(message)
                self.assertEqual(result.intent, expected)

    def test_intent_router_keeps_positive_signal_after_negated_clause(self) -> None:
        """A contrast clause must not inherit the first clause's negation."""
        router = IntentRouter()
        cases = {
            "不冒烟但漏水": ("safety_incident", "漏水"),
            "没有冒烟但是漏水": ("safety_incident", "漏水"),
            "不是故障而是漏水": ("safety_incident", "漏水"),
            "没有故障但噪音很大": ("troubleshooting", "噪音"),
        }
        for message, (expected_intent, expected_reason) in cases.items():
            with self.subTest(message=message):
                result = router.classify(message)
                self.assertEqual(result.intent, expected_intent)
                self.assertIn(expected_reason, result.reasons)

    def test_intent_router_pure_negation_has_no_positive_route(self) -> None:
        """Purely negative statements must not trigger safety or handoff routes."""
        router = IntentRouter()
        cases = (
            "没有冒烟，也不需要转人工",
            "我不需要维修，也没有故障",
            "无漏水、无冒烟、没有异常",
            "不要转人工，不需要售后",
        )
        for message in cases:
            with self.subTest(message=message):
                result = router.classify(message)
                self.assertEqual(result.intent, "general_support")
                self.assertNotIn("safety_incident", result.chain)
                self.assertNotIn("human_handoff", result.chain)

    def test_safety_signal_after_negation_creates_urgent_ticket(self) -> None:
        """A positive safety clause still escalates even when an earlier clause is negated."""
        service = AgentLoopService(store=self.store)
        result = asyncio.run(
            service.handle(
                AgentLoopRequest(
                    message="没有冒烟但是漏水，请马上转人工",
                    user_id="1001",
                )
            )
        )
        self.assertEqual(result.intent.intent, "safety_incident")
        self.assertIn("human_handoff", result.intent.secondary_intents)
        self.assertTrue(result.escalation_required)
        self.assertIsNotNone(result.ticket_id)
        self.assertEqual(self.store.ticket(result.ticket_id).priority, "urgent")  # type: ignore[union-attr]

    def test_purely_negated_safety_does_not_create_ticket(self) -> None:
        router = IntentRouter()
        service = AgentLoopService(store=self.store)
        result = asyncio.run(
            service.handle(
                AgentLoopRequest(
                    message="没有冒烟、没有漏水，也不需要转人工",
                    user_id="1001",
                )
            )
        )
        self.assertFalse(result.escalation_required)
        self.assertIsNone(result.ticket_id)

        # The negation phrase itself must not be mistaken for a boundary.
        self.assertEqual(router.classify("并非冒烟").intent, "general_support")

    def test_intent_router_keeps_multiword_model_name(self) -> None:
        result = IntentRouter().classify("型号是 S8 Pro，滤网堵塞")
        self.assertEqual(result.entities["model"], "S8 Pro")

    def test_ticket_lifecycle(self) -> None:
        ticket = self.store.create_ticket(TicketCreateRequest(subject="回充失败", description="持续无法回充"))
        self.assertEqual(ticket.status, "open")
        updated = self.store.update_ticket(ticket.id, TicketUpdateRequest(status="in_progress", assigned_to="after-sales"))
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "in_progress")  # type: ignore[union-attr]

    def test_long_term_memory_deduplicates_identical_facts(self) -> None:
        first = self.store.add_memory("1001", "c1", "long_term", "model", "S8")
        repeated = self.store.add_memory("1001", "c2", "long_term", "model", "S8")
        changed = self.store.add_memory("1001", "c2", "long_term", "model", "S9")
        self.assertEqual(first.id, repeated.id)
        self.assertNotEqual(first.id, changed.id)
        self.assertEqual(len(self.store.memories("1001", "long_term")), 2)

    def test_ticket_assignee_can_be_cleared_with_explicit_null(self) -> None:
        ticket = self.store.create_ticket(TicketCreateRequest(subject="回充失败", description="持续无法回充"))
        assigned = self.store.update_ticket(ticket.id, TicketUpdateRequest(assigned_to="agent-1"))
        self.assertEqual(assigned.assigned_to, "agent-1")  # type: ignore[union-attr]
        cleared = self.store.update_ticket(ticket.id, TicketUpdateRequest(assigned_to=None))
        self.assertIsNotNone(cleared)
        self.assertIsNone(cleared.assigned_to)  # type: ignore[union-attr]

    def test_memory_context_includes_recent_episodic_summary(self) -> None:
        self.store.add_memory("1001", "c1", "episodic", "intent", {"intent": "troubleshooting", "confidence": 0.7})
        _, profile = self.store.memory_context("1001", "c2")
        self.assertIn("近期事件", profile)
        self.assertIn("troubleshooting", profile)

    def test_loop_creates_urgent_ticket_and_layered_memory(self) -> None:
        service = AgentLoopService(store=self.store)
        result = asyncio.run(service.handle(AgentLoopRequest(message="机器冒烟了，请转人工", user_id="1001")))
        self.assertTrue(result.escalation_required)
        self.assertIsNotNone(result.ticket_id)
        self.assertEqual({item.memory_type for item in result.memories}, {"short_term", "episodic"})
        self.assertEqual(self.store.ticket(result.ticket_id).priority, "urgent")  # type: ignore[union-attr]

    def test_repeated_risk_message_reuses_active_conversation_ticket(self) -> None:
        service = AgentLoopService(store=self.store)
        first = asyncio.run(
            service.handle(
                AgentLoopRequest(
                    message="机器冒烟了，请转人工",
                    user_id="1001",
                    conversation_id="risk-conversation",
                )
            )
        )
        repeated = asyncio.run(
            service.handle(
                AgentLoopRequest(
                    message="机器仍在冒烟，请尽快处理",
                    user_id="1001",
                    conversation_id="risk-conversation",
                )
            )
        )

        self.assertEqual(first.ticket_id, repeated.ticket_id)
        self.assertEqual(len(self.store.list_tickets(user_id="1001")), 1)

    def test_default_evaluation_does_not_create_operational_tickets(self) -> None:
        service = AgentLoopService(store=self.store)
        run = asyncio.run(service.run_evaluation(EvaluationRunRequest()))

        self.assertEqual(run.count, len(service.default_evaluation_cases()))
        self.assertEqual(self.store.list_tickets(user_id="1001"), [])

    def test_automatic_score_prefers_relevant_safety_action_over_long_noise(self) -> None:
        relevant = self.store.score("机器冒烟怎么办", "请立即断电并停止使用，然后联系售后。")
        irrelevant = self.store.score("机器冒烟怎么办", "天气很好。" * 250)

        self.assertGreater(relevant, irrelevant)
        self.assertLessEqual(irrelevant, 0.2)

    def test_feedback_rating_is_used_as_quality_score(self) -> None:
        from backend.app.loop_schemas import EvaluationCreateRequest

        feedback = self.store.add_evaluation(
            EvaluationCreateRequest(
                question="主刷怎么清理？",
                answer="先断电，再拆下主刷清理毛发。",
                rating=5,
            )
        )
        self.assertEqual(feedback.score, 1.0)

    def test_negated_handoff_does_not_create_ticket(self) -> None:
        service = AgentLoopService(store=self.store)
        result = asyncio.run(service.handle(AgentLoopRequest(message="没有冒烟，也不需要转人工，但机器有噪音", user_id="1001")))
        self.assertFalse(result.escalation_required)
        self.assertIsNone(result.ticket_id)


if __name__ == "__main__":
    unittest.main()
