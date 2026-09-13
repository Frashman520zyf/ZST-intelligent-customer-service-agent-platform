from __future__ import annotations

import re
import importlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeHit:
    source: str
    content: str
    score: float


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    content: str
    terms: frozenset[str]


def _terms(value: str) -> set[str]:
    lowered = value.lower()
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", lowered)
    words.update(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    words.update(chinese)
    return words


def _read_pdf_text(path: Path) -> str | None:
    """Extract text from a PDF when an optional parser is installed.

    ``pypdf`` and ``PyPDF2`` are intentionally imported lazily so the backend
    remains usable without either package.  Parser/version errors are treated
    as an unavailable document and do not prevent the TXT knowledge base from
    loading.
    """

    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = importlib.import_module(module_name)
            reader_cls = getattr(module, "PdfReader", None) or getattr(
                module, "PdfFileReader", None
            )
            if reader_cls is None:
                continue
            reader = reader_cls(str(path))
            pages = getattr(reader, "pages", None)
            if pages is not None:
                page_count = len(pages)
                get_page = lambda index: pages[index]
            else:  # Older PyPDF2 API
                page_count = int(reader.getNumPages())
                get_page = reader.getPage
            text_parts: list[str] = []
            for index in range(page_count):
                try:
                    text_parts.append(get_page(index).extract_text() or "")
                except Exception:
                    continue
            text = "\n".join(text_parts).strip()
            if text:
                return text
        except Exception:
            continue
    return None


class KnowledgeBase:
    """Small dependency-free retriever over the project's existing TXT knowledge base."""

    def __init__(self, root: Path, chunk_size: int = 900, overlap: int = 120) -> None:
        self.root = root
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks = self._load()

    def _load(self) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        paths = sorted(self.root.rglob("*.txt")) + sorted(self.root.rglob("*.pdf"))
        for path in paths:
            if "external" in path.parts:
                continue
            if path.suffix.lower() == ".pdf":
                text = _read_pdf_text(path)
                if text is None:
                    continue
            else:
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
            start = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                content = text[start:end].strip()
                if content:
                    chunks.append(
                        KnowledgeChunk(
                            source=path.relative_to(self.root.parent).as_posix(),
                            content=content,
                            terms=frozenset(_terms(content)),
                        )
                    )
                if end >= len(text):
                    break
                start = max(start + 1, end - self.overlap)
        return chunks

    def search(self, query: str, limit: int = 4) -> list[KnowledgeHit]:
        query_terms = _terms(query)
        if not query_terms:
            return []
        scored: list[KnowledgeHit] = []
        for chunk in self.chunks:
            overlap = len(query_terms & chunk.terms)
            if overlap == 0:
                continue
            score = round(overlap / max(len(query_terms), 1), 3)
            scored.append(KnowledgeHit(chunk.source, chunk.content, score))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def context(self, query: str, limit: int = 4) -> tuple[str, list[KnowledgeHit]]:
        hits = self.search(query, limit)
        context = "\n\n".join(
            f"【参考资料{i}｜{hit.source}】\n{hit.content}"
            for i, hit in enumerate(hits, start=1)
        )
        return context, hits
