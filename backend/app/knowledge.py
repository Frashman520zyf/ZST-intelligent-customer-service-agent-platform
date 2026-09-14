"""Knowledge access facade backed by the durable hybrid retrieval index.

The original project exposed a tiny ``KnowledgeBase`` class.  Keeping that
facade means the existing chat agent remains compatible while the underlying
implementation gains page-aware PDF parsing, persistent TF-IDF/keyword
ranking, optional dense embeddings, stable citations and incremental rebuilds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import settings
from .retrieval import (
    DashScopeEmbeddingProvider,
    DocumentChunk,
    HashEmbeddingProvider,
    PersistentHybridIndex,
    RetrievalHit,
    TextChunker,
    tokenize,
)
from .rag_tools import RAGSearchTool, RAGToolResult


@dataclass(frozen=True)
class KnowledgeHit:
    source: str
    content: str
    score: float
    # Optional fields retain compatibility with the original three-field
    # ``KnowledgeHit(source, content, score)`` constructor.
    chunk_id: str | None = None
    citation: str | None = None
    metadata: dict[str, Any] | None = None
    lexical_score: float = 0.0
    keyword_score: float = 0.0
    vector_score: float = 0.0
    rank: int = 0


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    content: str
    terms: frozenset[str]
    metadata: dict[str, Any] | None = None


def _from_hit(hit: RetrievalHit) -> KnowledgeHit:
    return KnowledgeHit(
        chunk_id=hit.id,
        source=hit.source,
        content=hit.content,
        score=float(hit.score),
        citation=hit.citation,
        metadata=dict(hit.chunk.metadata),
        lexical_score=float(hit.lexical_score),
        keyword_score=float(hit.keyword_score),
        vector_score=float(hit.vector_score),
        rank=int(hit.rank),
    )


class KnowledgeBase:
    """Stable facade for retrieval, indexing and citation-aware contexts.

    ``DASHSCOPE_EMBEDDING_MODE=dashscope`` opts into the DashScope embedding
    endpoint.  The default ``hash`` provider is deterministic and offline,
    which keeps this demonstration runnable without a network or model
    download.  If a remote provider fails while building, lexical retrieval
    remains available automatically.
    """

    def __init__(
        self,
        root: Path,
        chunk_size: int = 900,
        overlap: int = 120,
        *,
        index_dir: Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.chunk_size = chunk_size
        self.overlap = overlap
        # Keep ad-hoc/test knowledge roots isolated.  The application passes a
        # project-level path explicitly; callers constructing a temporary base
        # get a local sibling index instead of sharing global runtime state.
        self.index_dir = Path(index_dir or (self.root / ".retrieval_index")).resolve()
        self.embedding_provider = self._embedding_provider()
        self.retriever = PersistentHybridIndex(
            self.root,
            index_dir=self.index_dir,
            embedding_provider=self.embedding_provider,
            chunker=TextChunker(chunk_size=chunk_size, overlap=overlap),
        )
        # Always perform a cheap incremental check on startup.  Besides new or
        # changed source files, ``PersistentHybridIndex`` also fingerprints the
        # chunking configuration, parser availability and embedding provider;
        # this lets installing PyMuPDF or switching embedding models refresh an
        # existing index without requiring a manual rebuild endpoint call.
        self.retriever.build(force=False)
        self.chunks = [self._chunk_from_document(chunk) for chunk in self.retriever.chunks]
        # Expose the auditable tool as part of the knowledge facade so both the
        # agent loop and API routes share exactly the same index and scoring
        # configuration.  The object remains valid across index rebuilds.
        self.rag_tool = RAGSearchTool(self.retriever)
        self.search_tool = self.rag_tool

    @staticmethod
    def _embedding_provider() -> Any:
        mode = settings.embedding_mode.strip().lower()
        if mode in {"dashscope", "remote", "api"} and settings.api_key:
            return DashScopeEmbeddingProvider(
                api_key=settings.api_key,
                model=settings.embedding_model,
                base_url=settings.dashscope_base_url,
            )
        return HashEmbeddingProvider(dimensions=settings.embedding_dimensions)

    @staticmethod
    def _chunk_from_document(chunk: DocumentChunk) -> KnowledgeChunk:
        return KnowledgeChunk(
            source=chunk.source,
            content=chunk.content,
            terms=frozenset(tokenize(chunk.content)),
            metadata=dict(chunk.metadata),
        )

    def rebuild(self, *, force: bool = True) -> dict[str, Any]:
        stats = self.retriever.rebuild() if force else self.retriever.build()
        self.chunks = [self._chunk_from_document(chunk) for chunk in self.retriever.chunks]
        return stats

    def stats(self) -> dict[str, Any]:
        return self.retriever.stats()

    def rag_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        max_chars: int | None = None,
        metadata_filter: Mapping[str, Any] | None = None,
        source: str | None = None,
        diversify_by_source: bool = True,
    ) -> RAGToolResult:
        """Run the shared citation-aware RAG tool against this knowledge base.

        ``source`` is a convenience filter for API callers; a general mapping
        can be supplied by orchestration code.  Both forms are passed to the
        same index and therefore produce identical ranking semantics.
        """

        filters = dict(metadata_filter or {})
        if source:
            filters["source"] = source
        return self.rag_tool.run(
            query,
            top_k=top_k or settings.retrieval_top_k,
            max_chars=max_chars if max_chars is not None else settings.retrieval_context_chars,
            metadata_filter=filters or None,
            diversify_by_source=diversify_by_source,
        )

    def search(self, query: str, limit: int = 4) -> list[KnowledgeHit]:
        result = self.rag_tool.run(
            query,
            top_k=limit,
            max_chars=settings.retrieval_context_chars,
            diversify_by_source=False,
        )
        return [_from_hit(hit) for hit in result.hits]

    def context(self, query: str, limit: int = 4) -> tuple[str, list[KnowledgeHit]]:
        result = self.rag_tool.run(
            query,
            top_k=limit,
            max_chars=settings.retrieval_context_chars,
            diversify_by_source=True,
        )
        return result.context, [_from_hit(hit) for hit in result.hits]
