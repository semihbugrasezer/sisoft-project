"""OpenAI-uyumlu `/v1/chat/completions` adaptörü. `LLMPort`'u `OllamaClient` ile aynı
şekilde sağlar; tek fark yapılandırılmış çıktının `response_format` (json_schema)
alanıyla istenmesi. Ollama'nın kendi OpenAI-uyumlu ucu, LM Studio ve vLLM ortak bu
protokolü konuşur — resmi dokümantasyonlarından doğrulandı (ctx7):
  - Ollama: /v1/chat/completions, response_format.type="json_schema" destekler
    (github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).
  - LM Studio ve vLLM aynı OpenAI response_format sözleşmesini uygular.
Canlı doğrulama: bkz. README.md → Deneysel Doğrulama.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.domain.errors import LLMOutputValidationError, LLMUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OpenAICompatibleClient:
    """`base_url` kökü `/v1` olmadan verilir (örn. `http://localhost:1234`);
    istemci `/v1/chat/completions`'ı kendisi ekler — Ollama'nın `/api/chat` alan
    adıyla aynı kurulum deneyimini korur."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        max_concurrency: int = 3,
        api_key: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0), headers=headers
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, payload: dict) -> str:
        try:
            async with self._semaphore:
                resp = await self._client.post(
                    f"{self._base_url}/v1/chat/completions", json=payload
                )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("OpenAI-uyumlu istek başarısız: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc
        try:
            content = resp.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message.content metin değil")
            return content
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("Geçersiz OpenAI-uyumlu yanıt: %s", exc)
            raise LLMUnavailableError("Sunucu geçerli bir yanıt döndürmedi.") from exc

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        return await self._post(
            {"model": self._model, "messages": messages, "temperature": temperature}
        )

    async def structured_chat(
        self,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.0,
        model: str | None = None,
    ) -> T:
        schema = response_model.model_json_schema()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        raw = await self._post(payload)
        try:
            return response_model.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as first_error:
            logger.info("Şema doğrulama hatası, retry deneniyor (%s)", type(first_error).__name__)
            retry_payload = dict(payload)
            retry_payload["messages"] = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Önceki yanıt şemaya uymadı: {first_error}\n"
                        "Lütfen SADECE verilen JSON şemasına uyan geçerli bir JSON döndür."
                    ),
                },
            ]
            raw2 = await self._post(retry_payload)
            try:
                return response_model.model_validate_json(raw2)
            except (ValidationError, json.JSONDecodeError) as second_error:
                raise LLMOutputValidationError(str(second_error)) from second_error
