"""Auditable RAG tools used by the orchestration layer and demo API.

Keeping retrieval behind a small tool object makes the agent flow explicit:
intent routing decides *which* tools to call, this object performs bounded
search/context assembly, and callers can emit the returned trace metadata to
the monitoring store.  It is intentionally synchronous because the local
index is in-process and CPU bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from collections.abc import Callable
from typing import Any, Mapping

from .retrieval import DocumentChunk, PersistentHybridIndex, RetrievalHit


@dataclass(frozen=True)
class RAGToolResult:
    query: str
    context: str
    hits: list[RetrievalHit]
    latency_ms: float
    strategy: str = "hybrid_tfidf_keyword_vector"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def citations(self) -> list[str]:
        return [hit.citation for hit in self.hits]

    def as_dict(self) -> dict[str, Any]:
        hits = [hit.as_dict() for hit in self.hits]
        return {
            "query": self.query,
            "context": self.context,
            "results": hits,
            # ``hits`` is the natural name for agent/tool callers; ``results``
            # remains available for existing API and frontend consumers.
            "hits": hits,
            "citations": self.citations,
            "latency_ms": round(self.latency_ms, 3),
            "strategy": self.strategy,
            "metadata": dict(self.metadata),
        }


class RAGSearchTool:
    """One bounded retrieval operation with traceable score components."""

    name = "knowledge_search"

    def __init__(self, index: PersistentHybridIndex) -> None:
        self.index = index

    def run(
        self,
        query: str,
        *,
        top_k: int = 5,
        max_chars: int = 6000,
        metadata_filter: Mapping[str, Any] | Callable[[DocumentChunk], bool] | None = None,
        diversify_by_source: bool = True,
    ) -> RAGToolResult:
        started = perf_counter()
        safe_query = (query or "").strip()[:4000]
        safe_top_k = max(1, min(int(top_k), 20))
        safe_max_chars = max(500, min(int(max_chars), 20000))
        context, hits = self.index.context(
            safe_query,
            top_k=safe_top_k,
            max_chars=safe_max_chars,
            metadata_filter=metadata_filter,
            diversify_by_source=diversify_by_source,
        ) if safe_query else ("", [])
        elapsed = (perf_counter() - started) * 1000
        return RAGToolResult(
            query=safe_query,
            context=context,
            hits=hits,
            latency_ms=elapsed,
            metadata={"index_ready": self.index.ready, "index_stats": self.index.stats()},
        )

    # A concise alias reads naturally in tool-calling code.
    search = run


RAGTool = RAGSearchTool


__all__ = ["RAGSearchTool", "RAGTool", "RAGToolResult"]
