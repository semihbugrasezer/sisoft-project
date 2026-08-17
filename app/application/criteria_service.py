"""Dinamik kriter tanımlama use-case (README.md §3)."""
from __future__ import annotations

import re

from app.domain.errors import LLMOutputValidationError, NoCriteriaDefinedError
from app.domain.models import CriteriaExtractionResult, CriteriaIntentResult, Criterion
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.prompts import CRITERIA_EXTRACTOR_SYSTEM, CRITERIA_INTENT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


class CriteriaService:
    def __init__(self, llm: OllamaClient, repo: SQLiteRepo):
        self._llm = llm
        self._repo = repo

    async def define_criteria(self, chat_id: int, free_text: str) -> list[Criterion]:
        result = await self._llm.structured_chat(
            CRITERIA_EXTRACTOR_SYSTEM, free_text, CriteriaExtractionResult
        )
        criteria = self._grounded_criteria(result.criteria, free_text)
        if not criteria:
            result = await self._llm.structured_chat(
                CRITERIA_EXTRACTOR_SYSTEM,
                free_text
                + "\n\nDÜZELTME: Her label kullanıcı metninden birebir kopyalanmış "
                "kesintisiz bir ifade olmalı; metinde olmayan kriterleri çıkar.",
                CriteriaExtractionResult,
            )
            criteria = self._grounded_criteria(result.criteria, free_text)
        if not criteria:
            raise LLMOutputValidationError("Model kullanıcı metninde olmayan kriter üretti.")
        return await self._save(chat_id, criteria)

    async def define_if_requested(
        self, chat_id: int, free_text: str
    ) -> list[Criterion] | None:
        result = await self._llm.structured_chat(
            CRITERIA_INTENT_SYSTEM, free_text, CriteriaIntentResult
        )
        if result.intent == "chat":
            return None
        criteria = self._grounded_criteria(result.criteria, free_text)
        if not criteria:
            return await self.define_criteria(chat_id, free_text)
        return await self._save(chat_id, criteria)

    async def _save(self, chat_id: int, criteria: list[Criterion]) -> list[Criterion]:
        await self._repo.set_criteria(chat_id, [criterion.model_dump() for criterion in criteria])
        return criteria

    @staticmethod
    def _grounded_criteria(criteria: list[Criterion], source: str) -> list[Criterion]:
        generic_words = {
            "beceri", "becerisi", "bilgi", "bilgisi", "deneyim", "deneyimi",
            "kriter", "tecrübe", "tecrübesi", "uyum", "uyumu", "uyumlu", "yetenek",
        }
        normalized_source = source.casefold()
        source_words = set(re.findall(r"\w+", normalized_source))

        def is_grounded(criterion: Criterion) -> bool:
            normalized_label = criterion.label.casefold().strip()
            exact_match = re.search(
                rf"(?<!\w){re.escape(normalized_label)}(?!\w)", normalized_source
            )
            return bool(exact_match) or any(
                word in source_words
                for word in re.findall(r"\w+", criterion.label.casefold())
                if len(word) >= 3 and word not in generic_words
            )

        return [criterion for criterion in criteria if is_grounded(criterion)]

    async def get_active_criteria(self, chat_id: int) -> list[Criterion]:
        raw = await self._repo.get_criteria(chat_id)
        if not raw:
            raise NoCriteriaDefinedError()
        return [Criterion.model_validate(c) for c in raw]
