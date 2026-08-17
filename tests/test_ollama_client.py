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
