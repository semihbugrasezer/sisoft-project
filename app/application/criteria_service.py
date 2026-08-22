"""Dinamik kriter tanımlama use-case (docs/LLM_PIPELINE.md)."""
from __future__ import annotations

import logging
import re

from app.domain.errors import (
    IntentUndecidableError,
    LLMOutputValidationError,
    NoCriteriaDefinedError,
)
from app.domain.models import CriteriaExtractionResult, CriteriaIntentResult, Criterion
from app.domain.ports import LLMPort
from app.infrastructure.llm.prompts import CRITERIA_EXTRACTOR_SYSTEM, CRITERIA_INTENT_SYSTEM
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo

logger = logging.getLogger(__name__)

_GENERIC_CRITERION_WORDS = {
    "beceri", "becerisi", "bilgi", "bilgisi", "deneyim", "deneyimi",
    "kriter", "tecrübe", "tecrübesi", "uyum", "uyumu", "uyumlu", "yetenek",
}


def _appears_in_words(word: str, words: set[str]) -> bool:
    return any(
        word == candidate
        or (len(word) >= 4 and candidate.startswith(word))
        or (len(candidate) >= 4 and word.startswith(candidate))
        for candidate in words
    )


def _criterion_label_key(label: str) -> frozenset[str]:
    label = label.replace("_", " ").replace("-", " ")
    meaningful = {
        word for word in re.findall(r"\w+", label.casefold())
        if len(word) >= 3 and word not in _GENERIC_CRITERION_WORDS
    }
    return frozenset(meaningful or {label.casefold().strip()})

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

    async def define_criteria(
        self,
        chat_id: int,
        free_text: str,
        seed_criteria: list[Criterion] | None = None,
    ) -> list[Criterion]:
        result = await self._llm.structured_chat(
            CRITERIA_EXTRACTOR_SYSTEM, free_text, CriteriaExtractionResult
        )
        candidates = [*(seed_criteria or []), *result.criteria]
        criteria: list[Criterion] = []
        seen_ids: set[str] = set()
        seen_label_keys: set[frozenset[str]] = set()

        def append_unique(candidates_to_add: list[Criterion]) -> None:
            for criterion in self._grounded_criteria(candidates_to_add, free_text):
                label_key = _criterion_label_key(criterion.label)
                if criterion.id not in seen_ids and label_key not in seen_label_keys:
                    criteria.append(criterion)
                    seen_ids.add(criterion.id)
                    seen_label_keys.add(label_key)

        append_unique(candidates)
        uncovered = self._uncovered_criterion_segments(criteria, free_text)
        if not criteria or uncovered:
            retry_sources = sorted(uncovered) if uncovered else [free_text]
            for retry_source in retry_sources:
                retry_result = await self._llm.structured_chat(
                    CRITERIA_EXTRACTOR_SYSTEM,
                    retry_source
                    + "\n\nDÜZELTME: Yalnızca yukarıdaki, önceki çıktının kapsamadığı "
                    "kriter parçasını çıkar. Önceki doğru etiketleri tekrar etme; "
                    "yalnızca kullanıcı metninde geçen ölçütü çıkar.",
                    CriteriaExtractionResult,
                )
                append_unique(retry_result.criteria)
                if not self._uncovered_criterion_segments(criteria, free_text):
                    break
        if not criteria:
            raise LLMOutputValidationError("Model kullanıcı metninde olmayan kriter üretti.")
        if self._uncovered_criterion_segments(criteria, free_text):
            raise LLMOutputValidationError("Model kullanıcı metnindeki tüm kriterleri çıkaramadı.")
        return await self._save(chat_id, criteria)

    @staticmethod
    def _uncovered_criterion_segments(
        criteria: list[Criterion], source: str
    ) -> set[str]:
        normalized_source = source.casefold()
        separator_pattern = r"[,;/\n]+|\b(?:ve|and)\b"
        # Tek "A ile B" çoğu zaman tek birleşik kriterdir. "A ile B ile C"
        # biçiminde ise tekrarlanan bağlaç açık bir liste davranışı gösterir.
        if len(re.findall(r"\bile\b", normalized_source)) >= 2:
            separator_pattern += r"|\bile\b"
        segments = [
            segment.strip()
            for segment in re.split(separator_pattern, normalized_source)
            if segment.strip()
        ]
        if len(segments) < 2:
            return set()

        label_words = {
            word
            for criterion in criteria
            for word in re.findall(r"\w+", criterion.label.casefold())
            if len(word) >= 3 and word not in _GENERIC_CRITERION_WORDS
        }
        return {
            segment
            for segment in segments
            if not any(
                _appears_in_words(label_word, set(re.findall(r"\w+", segment)))
                for label_word in label_words
            )
        }

    @staticmethod
    def _intent_undecidable(cause: LLMOutputValidationError) -> IntentUndecidableError:
        logger.warning("Intent sınıflandırması başarısız, kullanıcıya hata dönülüyor: %s", cause)
        return IntentUndecidableError(str(cause))

    async def define_if_requested(
        self, chat_id: int, free_text: str
    ) -> list[Criterion] | None:
        try:
            result = await self._llm.structured_chat(
                CRITERIA_INTENT_SYSTEM, free_text, CriteriaIntentResult, model=self._intent_model
            )
        except LLMOutputValidationError as first_error:
            # Niyet sınıflandırması şemaya uygun JSON üretemedi. Canlı testte zayıf
            # bir modelle (0.5B) gerçekleşti — bkz. docs/VALIDATION.md koşu #5.
            #
            # Burada "chat" varsaymak SESSİZ bir hatadır: kullanıcının kriter tanımı
            # sıradan bir sohbet mesajı gibi yanıtlanır, kriterler kaydedilmez ve
            # kullanıcı bunu ancak CV gönderdiğinde fark eder. Dinamik kriter
            # yakalama ödevin çekirdek gereksinimi olduğu için sessiz yanlış-mod
            # yerine açık hata tercih edilir.
            #
            # İsteğe bağlı küçük bir intent modeli yapılandırılmışsa önce ANA modelle
            # denenir — sorun büyük olasılıkla küçük modelin kapasitesidir.
            if self._intent_model is not None:
                logger.warning(
                    "Intent sınıflandırması şema hatası verdi (%s), ana modelle tekrar deneniyor",
                    self._intent_model,
                )
                try:
                    result = await self._llm.structured_chat(
                        CRITERIA_INTENT_SYSTEM, free_text, CriteriaIntentResult
                    )
                except LLMOutputValidationError as second_error:
                    raise self._intent_undecidable(second_error) from second_error
            else:
                raise self._intent_undecidable(first_error) from first_error
        if result.intent == "chat":
            return None
        # Intent çağrısının işi yalnız mesaj türünü belirlemek. Canlı model
        # koşularında birleşik intent+extraction çıktısı üç kriterden birini/ikisini
        # atlayabildi; kriterleri her zaman bu işe özel prompt ile yeniden çıkar.
        return await self.define_criteria(chat_id, free_text, result.criteria)

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
    def _grounded_criteria(criteria: list[Criterion], source: str) -> list[Criterion]:
        normalized_source = source.casefold()
        source_words = set(re.findall(r"\w+", normalized_source))

        def is_grounded(criterion: Criterion) -> bool:
            if CriteriaService._is_exact_label_match(criterion.label, normalized_source):
                return True
            label = criterion.label.replace("_", " ").replace("-", " ")
            meaningful_words = [
                word
                for word in re.findall(r"\w+", label.casefold())
                if len(word) >= 3
                and not word.isdigit()
                and word not in _GENERIC_CRITERION_WORDS
            ]
            return bool(meaningful_words) and all(
                _appears_in_words(word, source_words) for word in meaningful_words
            )

        grounded: list[Criterion] = []
        for criterion in criteria:
            label = re.sub(
                r"(?:n[ae])?\s+göre\s+(?:skorla|puanla|değerlendir)\s*$",
                "",
                criterion.label,
                flags=re.IGNORECASE,
            ).strip()
            normalized = criterion.model_copy(update={"label": label})
            if is_grounded(normalized):
                grounded.append(normalized)
        return grounded

    async def get_active_criteria(self, chat_id: int) -> list[Criterion]:
        raw = await self._repo.get_criteria(chat_id)
        if not raw:
            raise NoCriteriaDefinedError()
        return [Criterion.model_validate(c) for c in raw]
