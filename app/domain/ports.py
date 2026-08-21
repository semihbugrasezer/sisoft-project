"""LLM istemcisi için Protocol — application katmanı somut sınıfa değil bu arayüze
bağımlı olur (bkz. docs/ARCHITECTURE.md). `OllamaClient` ve
`OpenAICompatibleClient` (Ollama'nın kendi OpenAI-uyumlu ucu, LM Studio, vLLM) ikisi
de bu arayüzü sağlar; container.py hangisinin kurulacağına ortam değişkenine göre
karar verir, application servisleri hangi backend'in çalıştığını bilmez."""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMPort(Protocol):
    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str: ...

    async def structured_chat(
        self,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.0,
        model: str | None = None,
    ) -> T: ...

    async def aclose(self) -> None: ...
