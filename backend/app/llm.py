from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any

import httpx

from .config import settings


class DashScopeClient:
    def __init__(self) -> None:
        self.base_url = settings.dashscope_base_url.rstrip("/")
        self.model = settings.model

    @property
    def configured(self) -> bool:
        return bool(settings.api_key)

    async def complete(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str | None:
        if not self.configured:
            return None
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        try:
            # Keep the UI responsive when the external model endpoint is unavailable.
            async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return data["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError):
            return None

    async def stream(self, messages: list[dict[str, str]], temperature: float = 0.2) -> AsyncIterator[str]:
        if not self.configured:
            return
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0)) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:") or line.strip() == "data: [DONE]":
                            continue
                        data = json.loads(line[5:].strip())
                        delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
                        if delta:
                            yield delta
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return
