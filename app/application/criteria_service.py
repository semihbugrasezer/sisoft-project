"""Dinamik kriter tanımlama use-case (RULES.md §2, §5)."""
from __future__ import annotations

from app.domain.errors import NoCriteriaDefinedError
from app.domain.models import CriteriaExtractionResult, Criterion
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.prompts import CRITERIA_EXTRACTOR_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


class CriteriaService:
    def __init__(self, llm: OllamaClient, repo: SQLiteRepo):
        self._llm = llm
        self._repo = repo

    async def define_criteria(self, chat_id: int, free_text: str) -> list[Criterion]:
        result = await self._llm.structured_chat(
            CRITERIA_EXTRACTOR_SYSTEM, free_text, CriteriaExtractionResult
        )
        await self._repo.set_criteria(chat_id, [c.model_dump() for c in result.criteria])
        return result.criteria

    async def get_active_criteria(self, chat_id: int) -> list[Criterion]:
        raw = await self._repo.get_criteria(chat_id)
        if not raw:
            raise NoCriteriaDefinedError()
        return [Criterion.model_validate(c) for c in raw]
