import asyncio

import pytest

from app.domain.errors import LLMUnavailableError
from app.infrastructure.llm.ollama_client import OllamaClient


class InvalidResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"unexpected": True}


class FakeHTTPClient:
    async def post(self, *args, **kwargs):
        return InvalidResponse()


@pytest.mark.asyncio
async def test_malformed_success_response_becomes_controlled_error():
    client = OllamaClient("http://localhost:11434", "model", 1)
    original_client = client._client
    client._client = FakeHTTPClient()
    await original_client.aclose()

    with pytest.raises(LLMUnavailableError):
        await client.chat([{"role": "user", "content": "merhaba"}])


@pytest.mark.asyncio
async def test_max_concurrency_bounds_in_flight_requests():
    """Tek Ollama instance'ına aynı anda gidebilecek istek sayısı sınırlanmalı —
    Telegram concurrent_updates(8) ile aynı anda çok fazla istek yollanırsa bile."""
    in_flight = 0
    max_observed = 0
    lock = asyncio.Lock()

    class TrackingResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "ok"}}

    class TrackingHTTPClient:
        async def post(self, *args, **kwargs):
            nonlocal in_flight, max_observed
            async with lock:
                in_flight += 1
                max_observed = max(max_observed, in_flight)
            await asyncio.sleep(0.02)  # gerçek bir isteğin süresini simüle eder
            async with lock:
                in_flight -= 1
            return TrackingResponse()

    client = OllamaClient("http://localhost:11434", "model", 1, max_concurrency=2)
    original_client = client._client
    client._client = TrackingHTTPClient()
    await original_client.aclose()

    await asyncio.gather(*(client.chat([{"role": "user", "content": "x"}]) for _ in range(6)))

    assert max_observed <= 2
