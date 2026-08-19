"""Daily Chat use-case: backend'de korunan tam sohbet bağlamı (README.md §2).

Bağlam yönetimi iki katmanlı: son `CHAT_HISTORY_LIMIT` mesaj ham haliyle prompt'a
girer, penceresinin dışına taşan eski mesajlar ise silinmeden LLM ile bir "rolling
summary"ye katlanır ve system prompt'una eklenir. Böylece PDF'in "bağlam kaybolmayacak
şekilde" şartı uzun sohbetlerde de karşılanır — limitsiz gönderim, model context
window'unu taşırıp Ollama'nın sessizce baştan kırpmasına yol açıyordu (kontrolsüz kayıp).
"""
from __future__ import annotations

import asyncio
import logging

from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.prompts import CHAT_SUMMARIZER_SYSTEM, DAILY_CHAT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import CHAT_HISTORY_LIMIT, SQLiteRepo

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, llm: OllamaClient, repo: SQLiteRepo):
        self._llm = llm
        self._repo = repo
        self._chat_locks: dict[int, asyncio.Lock] = {}

    async def reply(self, chat_id: int, user_text: str) -> str:
        lock = self._chat_locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            await self._compact_overflow_into_summary(chat_id)

            summary = await self._repo.get_summary(chat_id)
            history = await self._repo.get_messages(chat_id)
            system = DAILY_CHAT_SYSTEM
            if summary:
                system += f"\n\nBu sohbetin daha eski bölümünün özeti:\n{summary}"

            messages = [
                {"role": "system", "content": system},
                *history,
                {"role": "user", "content": user_text},
            ]
            reply = await self._llm.chat(messages)
            await self._repo.add_message(chat_id, "user", user_text)
            await self._repo.add_message(chat_id, "assistant", reply)
            return reply

    async def _compact_overflow_into_summary(self, chat_id: int) -> None:
        """Bağlam penceresi dışına taşan mesajları mevcut özete katlar.

        Özetleme başarısız olursa sohbet akışı kesilmez — eski bağlam bu turda
        güncellenmemiş olur, bir sonraki mesajda tekrar denenir (mesajlar silinmediği
        ve `last_summarized_id` ilerletilmediği için veri kaybı olmaz).
        """
        overflow = await self._repo.get_unsummarized_overflow(chat_id, CHAT_HISTORY_LIMIT)
        if not overflow:
            return

        previous = await self._repo.get_summary(chat_id)
        transcript = "\n".join(f"{item['role']}: {item['content']}" for item in overflow)
        user_prompt = (
            (f"ÖNCEKİ ÖZET:\n{previous}\n\n" if previous else "")
            + f"SOHBETİN ESKİ BÖLÜMÜ:\n{transcript}"
        )

        try:
            summary = await self._llm.chat(
                [
                    {"role": "system", "content": CHAT_SUMMARIZER_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
        except Exception:
            logger.warning("Sohbet özeti üretilemedi, eski bağlam bu turda güncellenmedi",
                           exc_info=True)
            return

        await self._repo.set_summary(chat_id, summary.strip(), overflow[-1]["id"])
