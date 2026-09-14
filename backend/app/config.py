from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    model: str = os.getenv("DASHSCOPE_MODEL", "deepseek-v3")
    dashscope_base_url: str = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    allowed_origins: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    # Retrieval defaults are intentionally lightweight/offline.  Set
    # ``DASHSCOPE_EMBEDDING_MODE=dashscope`` to use the configured DashScope
    # embedding endpoint; failures fall back to lexical/hash retrieval.
    embedding_mode: str = os.getenv("DASHSCOPE_EMBEDDING_MODE", "hash")
    embedding_model: str = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")
    embedding_dimensions: int = int(os.getenv("HASH_EMBEDDING_DIMENSIONS", "384"))
    retrieval_context_chars: int = int(os.getenv("RETRIEVAL_CONTEXT_CHARS", "6000"))
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def knowledge_path(self) -> Path:
        return self.project_root / "data"

    @property
    def records_path(self) -> Path:
        return self.project_root / "data" / "external" / "records.csv"

    @property
    def prompts_path(self) -> Path:
        return self.project_root / "prompts"

    @property
    def retrieval_index_path(self) -> Path:
        return self.project_root / ".retrieval_index"

    @property
    def loop_db_path(self) -> Path:
        return self.project_root / "data" / "agent_loop.db"


settings = Settings()
