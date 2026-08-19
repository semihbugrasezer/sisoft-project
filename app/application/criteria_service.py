"""Dinamik kriter tanımlama use-case (README.md → Dinamik Kriter Tanımlama ve Tekli CV Analizi)."""
from __future__ import annotations

import re

from app.domain.errors import LLMOutputValidationError, NoCriteriaDefinedError
from app.domain.models import CriteriaExtractionResult, CriteriaIntentResult, Criterion
from app.domain.ports import LLMPort
from app.infrastructure.llm.prompts import CRITERIA_EXTRACTOR_SYSTEM, CRITERIA_INTENT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo

# NOT: Burada bir anahtar-kelime heuristic'i ile intent-classifier LLM çağrısını
# atlamayı denedik (düz sohbet mesajlarını hızlandırmak için) — ama
# test_free_text_without_keyword_can_define_criteria'yı kırdı: PDF açıkça
# "anahtar kelimesiz, tamamen serbest metinden kriter tanımlama" istiyor
# ("React tecrübesi benim için önemli" gibi bir cümlede "kriter/değerlendir/skorla"
# kelimesi geçmez ama kriter tanımıdır). Ucuz bir heuristic bunu güvenilir şekilde
# ayıramaz — yanlış negatif = sessizce kriter kaybı, rubric'in tam ölçtüğü yer.
# Çift-çağrı gecikmesi bunun yerine `intent_model` ile ele alınıyor (aşağıda):
# handlers.text_message hâlâ sıralı çalışır (önce intent, sonra chat — intent
# "criteria" çıkarsa chat çağrısı hiç yapılmaz, bu yüzden paralel başlatmak
# ikinci çağrının çoğu zaman gereksiz olacağı bir işi baştan yapmak demektir);
# gerçek hızlanma intent çağrısının kendisini küçük/hızlı bir modele taşımaktan
# gelir, bkz. `__init__`'teki `intent_model`.


class CriteriaService:
    def __init__(self, llm: LLMPort, repo: SQLiteRepo, intent_model: str | None = None):
        self._llm = llm
        self._repo = repo
        # Yalnız intent sınıflandırması (kriter mi/sohbet mi — ikili, basit görev) bu
        # modeli kullanır; asıl kriter çıkarımı (define_criteria) her zaman ana modelde
        # kalır çünkü daha karmaşık ve doğruluğu daha kritik.
        self._intent_model = intent_model

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
            CRITERIA_INTENT_SYSTEM, free_text, CriteriaIntentResult, model=self._intent_model
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
