from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.knowledge import KnowledgeBase
from backend.app.rag_tools import RAGSearchTool


class RAGToolIntegrationTests(unittest.TestCase):
    def test_knowledge_facade_exposes_shared_tool_and_citations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "guide.txt").write_text("主刷缠绕时先断电，再用剪刀清理毛发。", encoding="utf-8")
            base = KnowledgeBase(root, index_dir=Path(directory) / "index")

            self.assertIsInstance(base.rag_tool, RAGSearchTool)
            result = base.rag_search("主刷缠绕", top_k=2)
            self.assertTrue(result.hits)
            self.assertEqual(result.hits[0].source, "data/guide.txt")
            self.assertIn("data/guide.txt", result.citations[0])
            self.assertIn("strategy", result.as_dict())
            self.assertIn("latency_ms", result.as_dict())

    def test_tool_source_filter_is_applied_by_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "a.txt").write_text("滤网堵塞时清理滤网。", encoding="utf-8")
            (root / "b.txt").write_text("滤网更换周期为三个月。", encoding="utf-8")
            base = KnowledgeBase(root, index_dir=Path(directory) / "index")
            result = base.rag_tool.run("滤网", metadata_filter={"source": "data/b.txt"})
            self.assertTrue(result.hits)
            self.assertTrue(all(hit.source == "data/b.txt" for hit in result.hits))


if __name__ == "__main__":
    unittest.main()
