"""Smoke tests for the dependency-light production retrieval layer.

These tests use only the Python standard library and can be run with
``python -m unittest discover -s tests`` (pytest also discovers them).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.retrieval import (
    DocumentParser,
    HashEmbeddingProvider,
    PersistentHybridIndex,
    TextChunker,
    tokenize,
)


class RetrievalSmokeTests(unittest.TestCase):
    def test_tokenize_keeps_chinese_bigrams_and_model_codes(self) -> None:
        terms = tokenize("尘盒容量不足，型号 S8-Pro")
        self.assertIn("尘盒", terms)
        self.assertIn("容量", terms)
        self.assertIn("s8-pro", terms)

    def test_text_parser_and_page_aware_chunk_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.txt"
            path.write_text("第一段：清理尘盒。\n\n第二段：检查滤网。", encoding="utf-8")
            pages = DocumentParser().parse(path)
            self.assertEqual(len(pages), 1)
            chunks = TextChunker(chunk_size=12, overlap=2, min_chunk_size=1).chunk_pages(
                pages, source="data/guide.txt", file_hash="abc123", title="guide"
            )
            self.assertGreaterEqual(len(chunks), 2)
            self.assertEqual(chunks[0].metadata["file_hash"], "abc123")
            self.assertEqual(chunks[0].metadata["parser"], "text")
            self.assertIn("data/guide.txt", chunks[0].citation)

    def test_pdf_parser_is_optional_and_never_breaks_index(self) -> None:
        """A PDF without an installed parser is reported as empty, not fatal."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            # Minimal invalid PDF bytes exercise the graceful parser fallback;
            # valid PDF extraction is covered when pypdf/PyMuPDF is installed.
            (root / "manual.pdf").write_bytes(b"%PDF-1.4\nnot a real document")
            (root / "faq.txt").write_text("滤网清理方法", encoding="utf-8")
            index = PersistentHybridIndex(root, index_dir=Path(directory) / "idx")
            stats = index.rebuild()
            self.assertEqual(stats["sources"], 1)
            self.assertTrue(any(item["source"].endswith("manual.pdf") for item in stats["parse_errors"]))
            self.assertEqual(index.search("滤网", top_k=1)[0].source, "data/faq.txt")

    def test_build_search_context_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            index_dir = Path(directory) / "index"
            root.mkdir()
            (root / "a.txt").write_text("主刷缠绕毛发时请先断电，再用剪刀清理。", encoding="utf-8")
            (root / "b.txt").write_text("清理尘盒滤网并晾干，避免水分进入电机。", encoding="utf-8")

            provider = HashEmbeddingProvider(dimensions=32)
            index = PersistentHybridIndex(root, index_dir=index_dir, embedding_provider=provider)
            stats = index.rebuild()
            self.assertEqual(stats["sources"], 2)
            self.assertTrue(stats["dense_vectors"])
            hits = index.search("主刷 毛发", top_k=1)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].source, "data/a.txt")
            self.assertGreater(hits[0].score, 0)
            context, citations = index.context("尘盒滤网", top_k=2)
            self.assertTrue(context)
            self.assertEqual(len(citations), 2)
            self.assertIn("data/b.txt", context)

            restored = PersistentHybridIndex(root, index_dir=index_dir, embedding_provider=provider)
            self.assertTrue(restored.ready)
            self.assertEqual(restored.document_count, index.document_count)
            self.assertEqual(restored.build()["rebuilt"], False)

    def test_metadata_filter_and_source_diversification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "guide.txt").write_text("滤网清理方法。\n" * 30, encoding="utf-8")
            (root / "faq.txt").write_text("滤网堵塞报警处理。", encoding="utf-8")
            index = PersistentHybridIndex(root, index_dir=Path(directory) / "idx")
            index.rebuild()
            hits = index.search("滤网", top_k=10, diversify_by_source=True)
            self.assertLessEqual(len({hit.source for hit in hits}), len(hits))
            filtered = index.search("滤网", top_k=5, metadata_filter={"title": "faq"})
            self.assertTrue(filtered)
            self.assertTrue(all(hit.chunk.metadata.get("title") == "faq" for hit in filtered))

    def test_orthogonal_hash_vector_does_not_create_false_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "guide.txt").write_text(
                "brush filter maintenance instructions",
                encoding="utf-8",
            )
            index = PersistentHybridIndex(
                root,
                index_dir=Path(directory) / "idx",
                embedding_provider=HashEmbeddingProvider(dimensions=128),
            )
            index.rebuild()

            self.assertEqual(index.search("quantum banana", top_k=5), [])


if __name__ == "__main__":
    unittest.main()
