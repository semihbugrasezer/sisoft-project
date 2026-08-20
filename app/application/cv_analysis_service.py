"""Tekli ve batch CV akışı: validate -> extract -> evaluate (README.md → Nasıl Çalışıyor).

extract_text ve analyze_from_text ayrı metotlar: batch_analysis_service önce TÜM
dosyaları doğrulayıp sonra LLM'e geçmek istiyor (fail-fast), bu yüzden PDF
validation'ı ile LLM adımları ayrıştırılabilir olmalı. Batch yolu tüm profilleri
tek extraction çağrısında, tüm skorları yalnız normalize profillerden ikinci çağrıda üretir.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from app.domain.errors import LLMOutputValidationError
from app.domain.models import (
    BatchCandidateEvaluation,
    BatchEvaluationResult,
    BatchProfileResult,
    CandidateProfile,
    Criterion,
    EvaluationResult,
)
from app.domain.ports import LLMPort
from app.infrastructure.llm.prompts import CANDIDATE_EVALUATOR_SYSTEM, CV_EXTRACTOR_SYSTEM
from app.infrastructure.pdf.pymupdf_parser import validate_and_extract_text

logger = logging.getLogger(__name__)

# Sayfa/dosya boyutu için bilinçli olarak sabit bir limit koymuyoruz — PDF ödevi bunu
# belirtmiyor ve okunabilir bir CV'yi keyfi bir sayfa limitiyle reddetmek yanlış olur
# (bkz. test_readable_pdf_is_not_rejected_by_unspecified_page_or_text_limits). Ama
# LLM'e giden prompt'un boyutu context window/timeout riski taşır — o yüzden PDF'i
# reddetmeden, yalnızca modele giden metni burada sınırlıyoruz.
MAX_EXTRACTED_CHARS = 20_000


class CVAnalysisService:
    def __init__(self, llm: LLMPort):
        self._llm = llm

    async def extract_text(self, pdf_bytes: bytes) -> tuple[str, bool]:
        """Metni ve kırpılıp kırpılmadığını döner — kırpılmışsa çağıran (handlers.py)
        kullanıcıyı bilgilendirebilsin diye (belgenin sonundaki bilgi sessizce
        kaybolmasın)."""
        # Blocking PDF işi event loop'u bloklamasın diye thread'e atılır. max_chars
        # parser'a geçiriliyor ki bütçe dolar dolmaz sayfa okumayı durdursun —
        # PDF'i reddetmez, yalnızca gereksiz sayfa taramasını önler.
        text, truncated_by_parser = await asyncio.to_thread(
            validate_and_extract_text, pdf_bytes, max_chars=MAX_EXTRACTED_CHARS
        )
        # Parser sayfa sınırında durur, tam max_chars'ı garanti etmez (bir sayfa
        # bütçeyi aşabilir) — bu yüzden karakter bazlı kırpma burada ayrıca
        # uygulanır. truncated_by_parser, parser'ın kendisinin atladığı sayfa
        # olup olmadığını (bkz. pymupdf_parser.py) karakter sayımından daha
        # güvenilir şekilde bilir; ikisi OR'lanır.
        truncated = truncated_by_parser or len(text) > MAX_EXTRACTED_CHARS
        if truncated:
            logger.warning(
                "Çıkarılan metin %d karakter, %d'e kırpıldı (context/timeout koruması)",
                len(text), MAX_EXTRACTED_CHARS,
            )
            text = text[:MAX_EXTRACTED_CHARS]
        return text, truncated

    async def analyze_from_text(
        self, text: str, criteria: list[Criterion]
    ) -> tuple[CandidateProfile, EvaluationResult]:
        profile = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM, f"SOURCE_TEXT:\n{text}", CandidateProfile
        )

        criteria_json = "\n".join(
            f"- id={c.id}; label={c.label}; description={c.description}" for c in criteria
        )
        user_prompt = (
            f"CANDIDATE_PROFILE (JSON):\n{profile.model_dump_json()}\n\n"
            f"CRITERIA:\n{criteria_json}\n\n"
            "criterionId ve criterionLabel alanlarında yukarıdaki değerleri birebir kullan."
        )
        evaluation = await self._llm.structured_chat(
            CANDIDATE_EVALUATOR_SYSTEM, user_prompt, EvaluationResult
        )

        return profile, self._normalize_evaluation(evaluation, criteria)

    async def analyze_batch_from_texts(
        self, texts: list[str], criteria: list[Criterion]
    ) -> list[tuple[CandidateProfile, BatchCandidateEvaluation]]:
        # İki toplu LLM çağrısının süresi loglanır — batch tek yerel model
        # sunucusunda dakikalar sürebilir (bkz. docs/VALIDATION.md); bir isteğin
        # gerçekten ilerlediğini mi yoksa takılı mı kaldığını ayırt etmek için.
        documents = [
            {"documentId": document_id, "sourceText": text}
            for document_id, text in enumerate(texts)
        ]
        logger.info("Batch extraction başlıyor (%d belge)", len(texts))
        t0 = time.monotonic()
        profiles_result = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM
            + " Birden fazla belge verildiğinde her documentId için tam fakat öz bir profil üret.",
            "DOCUMENTS (JSON):\n" + json.dumps(documents, ensure_ascii=False),
            BatchProfileResult,
        )
        logger.info("Batch extraction bitti (%.1fs)", time.monotonic() - t0)
        profiles_by_id = self._items_by_document_id(
            profiles_result.candidates, len(texts)
        )

        normalized_profiles = [
            {
                "documentId": document_id,
                "profile": profiles_by_id[document_id].profile.model_dump(mode="json"),
            }
            for document_id in range(len(texts))
        ]
        criteria_data = [criterion.model_dump(mode="json") for criterion in criteria]
        logger.info("Batch evaluation başlıyor (%d belge)", len(texts))
        t0 = time.monotonic()
        evaluations_result = await self._llm.structured_chat(
            CANDIDATE_EVALUATOR_SYSTEM
            + " Birden fazla profil verildiğinde her documentId için bir değerlendirme üret.",
            "CANDIDATE_PROFILES (JSON):\n"
            + json.dumps(normalized_profiles, ensure_ascii=False)
            + "\n\nCRITERIA (JSON):\n"
            + json.dumps(criteria_data, ensure_ascii=False)
            + "\n\nHer documentId ile criterionId değerini birebir koru.",
            BatchEvaluationResult,
        )
        logger.info("Batch evaluation bitti (%.1fs)", time.monotonic() - t0)
        evaluations_by_id = self._items_by_document_id(
            evaluations_result.candidates, len(texts)
        )

        return [
            (
                profiles_by_id[document_id].profile,
                evaluations_by_id[document_id].evaluation.model_copy(
                    update={
                        "scores": self._normalize_scores(
                            evaluations_by_id[document_id].evaluation.scores, criteria
                        )
                    }
                ),
            )
            for document_id in range(len(texts))
        ]

    @staticmethod
    def _items_by_document_id(items, expected_count: int):
        by_id = {item.documentId: item for item in items}
        expected_ids = set(range(expected_count))
        if len(by_id) != len(items) or set(by_id) != expected_ids:
            raise LLMOutputValidationError("Model her belge için tek bir sonuç üretmedi.")
        return by_id

    @staticmethod
    def _normalize_evaluation(
        evaluation: EvaluationResult, criteria: list[Criterion]
    ) -> EvaluationResult:
        return evaluation.model_copy(
            update={"scores": CVAnalysisService._normalize_scores(evaluation.scores, criteria)}
        )

    @staticmethod
    def _normalize_scores(scores, criteria: list[Criterion]):
        scores_by_id = {score.criterionId: score for score in scores}
        expected_ids = {criterion.id for criterion in criteria}
        if len(scores_by_id) != len(scores) or set(scores_by_id) != expected_ids:
            raise LLMOutputValidationError("Model kriterlerin her biri için tek bir skor üretmedi.")

        return [
            scores_by_id[criterion.id].model_copy(
                update={"criterionLabel": criterion.label}
            )
            for criterion in criteria
        ]

    async def analyze(
        self, pdf_bytes: bytes, criteria: list[Criterion]
    ) -> tuple[CandidateProfile, EvaluationResult, bool]:
        text, truncated = await self.extract_text(pdf_bytes)
        profile, evaluation = await self.analyze_from_text(text, criteria)
        return profile, evaluation, truncated
