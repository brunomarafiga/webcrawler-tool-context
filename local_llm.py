from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class _Response:
    text: str


class _Models:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate_content(
        self,
        model: str,
        contents: str,
        config: Any = None,
    ) -> _Response:
        temperature = getattr(config, "temperature", 0.3)
        response_mime_type = getattr(config, "response_mime_type", None)

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": [{"role": "user", "content": contents}],
            "stream": False,
            "options": {
                "temperature": float(temperature if temperature is not None else 0.3),
            },
        }
        if response_mime_type == "application/json":
            payload["format"] = "json"

        response = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=httpx.Timeout(300.0),
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("message", {}).get("content", "")
        return _Response(text=text)


class LocalLLMClient:
    """Small adapter that exposes the subset used by the pipeline."""

    def __init__(self, base_url: str, model: str) -> None:
        self.models = _Models(base_url, model)
