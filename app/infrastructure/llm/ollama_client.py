"""Ollama /api/chat adapter. Structured output için Pydantic JSON Schema kullanılır
(prompt içine 'JSON döndür' yazmaktan daha güvenilir). Bkz. docs/ARCHITECTURE.md.
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


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float, max_concurrency: int = 3):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0))
        # Telegram tarafı concurrent_updates(8) ile eşzamanlı update kabul eder, ama
        # tek yerel Ollama instance'ı bunları paralel işleyemez — sınırsız istek
        # gönderilirse hepsi sunucu tarafında kuyruklanır (yanıt vermeye devam etme
        # garantisi bozulmaz ama gecikme öngörülemez büyür). Bu semaphore, kaç isteğin
        # aynı anda "uçuşta" olabileceğini backend'de sınırlar.
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post_chat(
        self,
        messages: list[dict],
        format_: str | dict | None,
        temperature: float,
        model: str | None = None,
    ) -> str:
        payload = {
            "model": model or self._model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature},
        }
        if format_ is not None:
            payload["format"] = format_
        try:
            async with self._semaphore:
                resp = await self._client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Ollama isteği başarısız: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc
        try:
            content = resp.json()["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message.content metin değil")
            return content
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Ollama geçersiz yanıt döndürdü: %s", exc)
            raise LLMUnavailableError("Ollama geçerli bir yanıt döndürmedi.") from exc

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """Serbest metin sohbet (Daily Chat modu) — şema yok."""
        return await self._post_chat(messages, format_=None, temperature=temperature)

    async def structured_chat(
        self,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.0,
        model: str | None = None,
    ) -> T:
        """Sistem+kullanıcı promptuyla çağırır, çıktıyı response_model'e doğrular.
        Şema hatasında bir kez düzeltme denenir, sonra LLMOutputValidationError.

        `model`: verilmezse `__init__`'teki ana model kullanılır. İsteğe bağlı override —
        örn. intent-classification gibi basit/ikili görevler için daha küçük/hızlı bir
        model (`LLM_INTENT_MODEL`) geçirilebilir; extraction/evaluation gibi karmaşık
        görevler ana modelde kalmaya devam eder."""
        schema = response_model.model_json_schema()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = await self._post_chat(messages, format_=schema, temperature=temperature, model=model)
        try:
            return response_model.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as first_error:
            logger.info(
                "Şema doğrulama hatası, retry deneniyor (%s)",
                type(first_error).__name__,
            )
            retry_messages = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Önceki yanıt şemaya uymadı: {first_error}\n"
                        "Lütfen SADECE verilen JSON şemasına uyan geçerli bir JSON döndür."
                    ),
                },
            ]
            raw2 = await self._post_chat(
                retry_messages, format_=schema, temperature=temperature, model=model
            )
            try:
                return response_model.model_validate_json(raw2)
            except (ValidationError, json.JSONDecodeError) as second_error:
                raise LLMOutputValidationError(str(second_error)) from second_error
