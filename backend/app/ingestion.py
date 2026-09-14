"""Stable ingestion-facing API.

The implementation lives in :mod:`backend.app.retrieval`; this module keeps
document ingestion imports discoverable and leaves room for future upload/OCR
adapters without coupling callers to the index internals.
"""

from __future__ import annotations

from pathlib import Path

from .retrieval import DocumentChunk, DocumentParser, PageText, TextChunker


def extract_document(path: str | Path, *, parser: DocumentParser | None = None) -> list[PageText]:
    """Extract page-aware text from a UTF text or PDF document."""

    document = Path(path)
    if not document.exists():
        raise FileNotFoundError(document)
    if not document.is_file():
        raise IsADirectoryError(document)
    return (parser or DocumentParser()).parse(document)


def chunk_document(
    pages: list[PageText] | tuple[PageText, ...],
    *,
    source: str,
    file_hash: str,
    chunk_size: int = 900,
    overlap: int = 120,
    title: str | None = None,
) -> list[DocumentChunk]:
    """Chunk extracted pages while retaining citation metadata."""

    return TextChunker(chunk_size=chunk_size, overlap=overlap).chunk_pages(
        pages, source=source, file_hash=file_hash, title=title
    )


__all__ = ["DocumentChunk", "DocumentParser", "PageText", "chunk_document", "extract_document"]
