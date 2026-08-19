import asyncio

import pytest
from pydantic import BaseModel

from app.domain.errors import LLMUnavailableError, LLMOutputValidationError
from app.infrastructure.llm.openai_compatible_client import OpenAICompatibleClient


class Answer(BaseModel):
    value: str


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
    client = OpenAICompatibleClient("http://localhost:1234", "model", 1)
    original_client = client._client
    client._client = FakeHTTPClient()
    await original_client.aclose()

    with pytest.raises(LLMUnavailableError):
        await client.chat([{"role": "user", "content": "merhaba"}])


@pytest.mark.asyncio
async def test_structured_chat_sends_openai_response_format_and_parses_choices():
    """OpenAI-uyumlu sözleşme: response_format.type=json_schema gönderilir,
    yanıt choices[0].message.content'ten okunur (Ollama'nın düz message.content'inden
    farklı zarf yapısı)."""
    captured_payload = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"value": "ok"}'}}]}

    class RecordingHTTPClient:
        async def post(self, url, json):
            captured_payload["url"] = url
            captured_payload["json"] = json
            return Response()

    client = OpenAICompatibleClient("http://localhost:1234", "model", 1)
    original_client = client._client
    client._client = RecordingHTTPClient()
    await original_client.aclose()

    result = await client.structured_chat("system", "user", Answer)

    assert result == Answer(value="ok")
    assert captured_payload["url"] == "http://localhost:1234/v1/chat/completions"
    fmt = captured_payload["json"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "Answer"
    assert fmt["json_schema"]["schema"] == Answer.model_json_schema()


@pytest.mark.asyncio
async def test_structured_chat_retries_once_then_raises_on_persistent_invalid_json():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    class AlwaysInvalidHTTPClient:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    client = OpenAICompatibleClient("http://localhost:1234", "model", 1)
    original_client = client._client
    fake = AlwaysInvalidHTTPClient()
    client._client = fake
    await original_client.aclose()

    with pytest.raises(LLMOutputValidationError):
        await client.structured_chat("system", "user", Answer)
    assert fake.calls == 2  # ilk deneme + tek retry


@pytest.mark.asyncio
async def test_max_concurrency_bounds_in_flight_requests():
    in_flight = 0
    max_observed = 0
    lock = asyncio.Lock()

    class TrackingResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class TrackingHTTPClient:
        async def post(self, *args, **kwargs):
            nonlocal in_flight, max_observed
            async with lock:
                in_flight += 1
                max_observed = max(max_observed, in_flight)
            await asyncio.sleep(0.02)
            async with lock:
                in_flight -= 1
            return TrackingResponse()

    client = OpenAICompatibleClient("http://localhost:1234", "model", 1, max_concurrency=2)
    original_client = client._client
    client._client = TrackingHTTPClient()
    await original_client.aclose()

    await asyncio.gather(*(client.chat([{"role": "user", "content": "x"}]) for _ in range(6)))

    assert max_observed <= 2


def test_optional_api_key_sets_bearer_header():
    client = OpenAICompatibleClient("http://localhost:1234", "model", 1, api_key="secret")
    assert client._client.headers["authorization"] == "Bearer secret"


def test_no_api_key_by_default():
    client = OpenAICompatibleClient("http://localhost:1234", "model", 1)
    assert "authorization" not in client._client.headers
