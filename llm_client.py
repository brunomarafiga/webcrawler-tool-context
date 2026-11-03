"""Clientes de geração para os provedores suportados pelo pipeline."""

from __future__ import annotations

from typing import Protocol

import httpx
from google import genai


class LLMClient(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        """Gera texto a partir de um prompt."""


class GeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        config_kwargs: dict[str, object] = {"temperature": temperature}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(**config_kwargs),
        )
        return (response.text or "").strip()


class OllamaClient:
    def __init__(self, host: str, model: str, timeout: float) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=timeout)

    def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        response = self._client.post(f"{self._host}/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        text = result.get("response")
        if not isinstance(text, str):
            raise RuntimeError("O Ollama retornou uma resposta sem texto.")
        return text.strip()


def create_llm_client(
    provider: str,
    *,
    gemini_api_key: str | None,
    gemini_model: str,
    ollama_host: str,
    ollama_model: str,
    ollama_timeout: float,
) -> LLMClient:
    if provider == "ollama":
        return OllamaClient(ollama_host, ollama_model, ollama_timeout)
    if provider == "gemini":
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY não configurada.")
        return GeminiClient(gemini_api_key, gemini_model)
    raise ValueError(f"Provedor LLM não suportado: {provider}")