"""Daily Chat use-case: context korunan sohbet (RULES.md §1)."""
from __future__ import annotations

from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.prompts import DAILY_CHAT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


class ChatService:
    def __init__(self, llm: OllamaClient, repo: SQLiteRepo, history_limit: int):
        self._llm = llm
        self._repo = repo
        self._history_limit = history_limit

    async def reply(self, chat_id: int, user_text: str) -> str:
        history = await self._repo.get_recent_messages(chat_id, self._history_limit)
        messages = [
            {"role": "system", "content": DAILY_CHAT_SYSTEM},
            *history,
            {"role": "user", "content": user_text},
        ]
        reply = await self._llm.chat(messages)
        await self._repo.add_message(chat_id, "user", user_text)
        await self._repo.add_message(chat_id, "assistant", reply)
        return reply
