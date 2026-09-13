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


settings = Settings()
