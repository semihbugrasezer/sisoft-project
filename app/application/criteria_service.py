"""Dinamik kriter tanımlama use-case (README.md → Dinamik Kriter Tanımlama ve Tekli CV Analizi)."""
from __future__ import annotations

import logging
import re

from app.domain.errors import LLMOutputValidationError, NoCriteriaDefinedError
from app.domain.models import CriteriaExtractionResult, CriteriaIntentResult, Criterion
from app.domain.ports import LLMPort
from app.infrastructure.llm.prompts import CRITERIA_EXTRACTOR_SYSTEM, CRITERIA_INTENT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo

logger = logging.getLogger(__name__)

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
        if not criteria or not self._all_labels_exact(criteria, free_text):
            # En az bir label kullanıcı metninden birebir değilse (LLM parafraz etmiş
            # olabilir, örn. "React tecrübesi" -> "React deneyimi") bir kez daha,
            # daha açık bir talimatla denenir. Ödev PDF'indeki örnek JSON, kullanıcının
            # kendi ifadesinin birebir yansıtılmasını bekliyor.
            retry_result = await self._llm.structured_chat(
                CRITERIA_EXTRACTOR_SYSTEM,
                free_text
                + "\n\nDÜZELTME: Her label kullanıcı metninden birebir kopyalanmış "
                "kesintisiz bir ifade olmalı; metinde olmayan kriterleri çıkar.",
                CriteriaExtractionResult,
            )
            retried = self._grounded_criteria(retry_result.criteria, free_text)
            # Retry tamamen boşsa ilk (parafrazlı ama en azından anahtar kelime bazlı
            # grounded) sonuca düşülür — model'i tamamen reddetmek yerine.
            if retried:
                criteria = retried
        if not criteria:
            raise LLMOutputValidationError("Model kullanıcı metninde olmayan kriter üretti.")
        return await self._save(chat_id, criteria)

    async def define_if_requested(
        self, chat_id: int, free_text: str
    ) -> list[Criterion] | None:
        try:
            result = await self._llm.structured_chat(
                CRITERIA_INTENT_SYSTEM, free_text, CriteriaIntentResult, model=self._intent_model
            )
        except LLMOutputValidationError:
            # Niyet sınıflandırması şemaya uygun JSON üretemedi (iki denemede de) —
            # canlı testte zayıf bir modelle (0.5B) gerçekleşti, bkz. README.md →
            # Teknik Altyapı. Kullanıcıyı hata mesajıyla çıkmaza sokmak yerine mesajı
            # "chat" varsayıp normal sohbete düşürüyoruz: kriter tanımlamak isteyen
            # kullanıcı ya modelin sonraki denemede doğru sınıflandırmasıyla ya da
            # açık `/criteria` komutuyla amacına ulaşır — hard-fail yerine soft-fail.
            logger.warning(
                "Intent sınıflandırması şema hatası verdi, mesaj chat olarak işleniyor"
            )
            return None
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
    def _is_exact_label_match(label: str, normalized_source: str) -> bool:
        normalized_label = label.casefold().strip()
        return bool(
            re.search(rf"(?<!\w){re.escape(normalized_label)}(?!\w)", normalized_source)
        )

    @staticmethod
    def _all_labels_exact(criteria: list[Criterion], source: str) -> bool:
        """Ödev PDF'indeki örnek JSON, `userDefinedCriteria`/`dynamicScores` alanlarında
        kullanıcının kendi ifadesinin birebir yansımasını bekliyor. Bu, `define_criteria`
        içinde bir düzeltme turu tetiklemek için kullanılır — parafraz edilmiş bir label
        (örn. "React tecrübesi" -> "React deneyimi") grounded sayılsa bile burada False
        döner."""
        normalized_source = source.casefold()
        return all(
            CriteriaService._is_exact_label_match(criterion.label, normalized_source)
            for criterion in criteria
        )

    @staticmethod
    def _grounded_criteria(criteria: list[Criterion], source: str) -> list[Criterion]:
        generic_words = {
            "beceri", "becerisi", "bilgi", "bilgisi", "deneyim", "deneyimi",
            "kriter", "tecrübe", "tecrübesi", "uyum", "uyumu", "uyumlu", "yetenek",
        }
        normalized_source = source.casefold()
        source_words = set(re.findall(r"\w+", normalized_source))

        def is_grounded(criterion: Criterion) -> bool:
            return CriteriaService._is_exact_label_match(
                criterion.label, normalized_source
            ) or any(
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
