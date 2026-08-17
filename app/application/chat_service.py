"""Daily Chat use-case: backend'de korunan tam sohbet bağlamı (README.md §2)."""
from __future__ import annotations

import asyncio

from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.prompts import DAILY_CHAT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


class ChatService:
    def __init__(self, llm: OllamaClient, repo: SQLiteRepo):
        self._llm = llm
        self._repo = repo
        self._chat_locks: dict[int, asyncio.Lock] = {}

    async def reply(self, chat_id: int, user_text: str) -> str:
        lock = self._chat_locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            history = await self._repo.get_messages(chat_id)
            messages = [
                {"role": "system", "content": DAILY_CHAT_SYSTEM},
                *history,
                {"role": "user", "content": user_text},
            ]
            reply = await self._llm.chat(messages)
            await self._repo.add_message(chat_id, "user", user_text)
            await self._repo.add_message(chat_id, "assistant", reply)
            return reply
