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
async def test_chat_disables_model_thinking():
    captured_payload = {}

    class ValidResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "ok"}}

    class RecordingHTTPClient:
        async def post(self, *args, **kwargs):
            captured_payload.update(kwargs["json"])
            return ValidResponse()

    client = OllamaClient("http://localhost:11434", "model", 1)
    original_client = client._client
    client._client = RecordingHTTPClient()
    await original_client.aclose()

    await client.chat([{"role": "user", "content": "merhaba"}])

    assert captured_payload["think"] is False


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


@pytest.mark.asyncio
async def test_context_length_is_sent_explicitly():
    """num_ctx gönderilmezse Ollama kendi varsayılanına (tipik 4096) düşer.

    Canlı 5 CV koşusunda girdi 2100 token'da kalıyordu ama üretim 2765 token
    sürüyordu: toplam 4865 > 4096. Pencere ÜRETİM sırasında taşınca model son
    belgenin kaynağını kaybedip ilk belgenin profilini birebir tekrarladı.
    Batch bütçesi (MAX_BATCH_EXTRACTED_CHARS) zaten 32k context varsayıyor;
    bu test o varsayımın modele gerçekten iletildiğini sabitler.
    """
    captured_payload = {}

    class ValidResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "ok"}}

    class RecordingHTTPClient:
        async def post(self, *args, **kwargs):
            captured_payload.update(kwargs["json"])
            return ValidResponse()

    client = OllamaClient("http://localhost:11434", "model", 1, context_length=32768)
    original_client = client._client
    client._client = RecordingHTTPClient()
    await original_client.aclose()

    await client.chat([{"role": "user", "content": "merhaba"}])

    assert captured_payload["options"]["num_ctx"] == 32768


@pytest.mark.asyncio
async def test_context_exhaustion_is_logged(caplog):
    """Taşma sessiz kalmamalı: prompt+üretim pencereyi doldurduysa uyar."""

    class FullWindowResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "ok"}, "prompt_eval_count": 2100, "eval_count": 2765}

    class FullWindowHTTPClient:
        async def post(self, *args, **kwargs):
            return FullWindowResponse()

    client = OllamaClient("http://localhost:11434", "model", 1, context_length=4096)
    original_client = client._client
    client._client = FullWindowHTTPClient()
    await original_client.aclose()

    with caplog.at_level("WARNING"):
        await client.chat([{"role": "user", "content": "merhaba"}])

    assert "Context penceresi doldu" in caplog.text
    assert "4865/4096" in caplog.text
