"""Tekli ve batch CV akışı: validate -> extract -> evaluate (docs/LLM_PIPELINE.md).

extract_text ve analyze_from_text ayrı metotlar: batch_analysis_service önce TÜM
dosyaları doğrulayıp sonra LLM'e geçmek istiyor (all-or-nothing ön doğrulama),
bu yüzden PDF validation'ı ile LLM adımları ayrıştırılabilir olmalı. Batch yolu tüm profilleri
tek extraction çağrısında, tüm skorları yalnız normalize profillerden ikinci çağrıda üretir.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from app.domain.errors import LLMOutputValidationError
from app.domain.grounding import (
    is_grounded_claim_in_source,
    is_grounded_in_source,
)
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

# Batch akışında TÜM belgeler tek prompt'a girer. Belge başına limit tek başına
# yetmez: 5 × 20.000 = 100.000 karakterlik bir prompt tipik bir yerel modelin
# context window'unu (örn. 32k token ≈ 90-120k karakter) taşırabilir ve model
# baştaki belgeleri sessizce kırpar. Bu yüzden batch için ayrı bir toplam bütçe
# var; aşılırsa belge başına pay eşit olarak küçültülür.
# ponytail: karakter bazlı bütçe, token bazlı değil — tokenizer'a bağımlılık
# eklememek için kasıtlı basit tutuldu. Gerçek token sayımı gerekirse
# tiktoken/HF tokenizer ile burada değiştirilir.
MAX_BATCH_EXTRACTED_CHARS = 60_000


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
        profile = await self._ground_candidate_name(profile, text)
        profile = self._ground_profile_skills(profile, text)

        criteria_json = "\n".join(
            f"- id={c.id}; label={c.label}; description={c.description}; "
            f"evidenceHints={', '.join(c.evidenceHints) or 'yok'}"
            for c in criteria
        )
        user_prompt = (
            f"CANDIDATE_PROFILE (JSON):\n{profile.model_dump_json()}\n\n"
            f"CRITERIA:\n{criteria_json}\n\n"
            "criterionId ve criterionLabel alanlarında yukarıdaki değerleri birebir kullan."
        )
        evaluation = await self._llm.structured_chat(
            CANDIDATE_EVALUATOR_SYSTEM, user_prompt, EvaluationResult
        )

        return profile, self._normalize_evaluation(evaluation, criteria, profile, text)

    async def _ground_candidate_name(
        self, profile: CandidateProfile, source_text: str
    ) -> CandidateProfile:
        """`candidateName` kaynak metinde geçmiyorsa bir kez düzeltme turu dener;
        yine tutmazsa alanı None yapar.

        Gerekçe: canlı testte model Türkçe aksanlı bir ismi bozdu ("Buğra" →
        "Bügüra"). Bozuk bir adı sessizce kabul etmek, uydurulmuş veriyi rapora
        taşımak demektir. None dönmek güvenlidir çünkü çağıranlar zaten dosya adına
        düşer (`profile.candidateName or filename`)."""
        if profile.candidateName is None:
            return profile  # model zaten "ad yok" demiş — uydurma riski yok
        if is_grounded_in_source(profile.candidateName, source_text):
            return profile

        logger.warning(
            "candidateName kaynak metinde bulunamadı (%r) — düzeltme turu deneniyor",
            profile.candidateName,
        )
        retried = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM
            + " DÜZELTME: candidateName alanı SOURCE_TEXT içinde birebir geçen bir"
            " ifade olmalıdır; harf değiştirme/tahmin yapma. Ad gerçekten yoksa null yaz.",
            f"SOURCE_TEXT:\n{source_text}",
            CandidateProfile,
        )
        if is_grounded_in_source(retried.candidateName, source_text):
            return retried

        logger.warning(
            "candidateName ikinci denemede de doğrulanamadı (%r) — None'a çekiliyor",
            retried.candidateName,
        )
        return retried.model_copy(update={"candidateName": None})

    @staticmethod
    def _ground_profile_skills(
        profile: CandidateProfile, source_text: str
    ) -> CandidateProfile:
        grounded = [
            skill for skill in profile.skills
            if is_grounded_in_source(skill, source_text)
        ]
        if len(grounded) == len(profile.skills):
            return profile
        logger.warning(
            "Kaynakta bulunmayan %d skill normalize profilden çıkarıldı",
            len(profile.skills) - len(grounded),
        )
        return profile.model_copy(update={"skills": grounded})

    @staticmethod
    def fit_batch_budget(texts: list[str]) -> tuple[list[str], list[int]]:
        """Toplam batch metni `MAX_BATCH_EXTRACTED_CHARS`'ı aşarsa belge başına eşit
        paya kırpar. Kısa belgeler kendi boyutlarında kalır; yalnızca payını aşanlar
        kırpılır, böylece bir uzun CV kısa olanların yerini yemez.

        `(kırpılmış_metinler, kırpılan_belge_indeksleri)` döner. İkinci değer önemli:
        dosya başına 20k limitini aşmayan belgeler bile burada kırpılabilir (5×15k =
        75k > 60k) ve kullanıcı bundan haberdar edilmelidir — aksi halde sessiz veri
        kaybı olur (bkz. BatchAnalysisService.analyze_batch)."""
        total = sum(len(text) for text in texts)
        if total <= MAX_BATCH_EXTRACTED_CHARS or not texts:
            return texts, []

        share = MAX_BATCH_EXTRACTED_CHARS // len(texts)
        # Payını kullanmayan belgelerden artan bütçeyi, aşanlara yeniden dağıt.
        spare = sum(share - len(text) for text in texts if len(text) < share)
        over = [text for text in texts if len(text) > share]
        bonus = spare // len(over) if over else 0

        logger.warning(
            "Batch metni %d karakter, %d bütçesine kırpılıyor (%d belge)",
            total, MAX_BATCH_EXTRACTED_CHARS, len(texts),
        )
        fitted: list[str] = []
        trimmed: list[int] = []
        for index, text in enumerate(texts):
            if len(text) <= share:
                fitted.append(text)
            else:
                fitted.append(text[: share + bonus])
                trimmed.append(index)
        return fitted, trimmed

    async def analyze_batch_from_texts(
        self, texts: list[str], criteria: list[Criterion]
    ) -> list[tuple[CandidateProfile, BatchCandidateEvaluation]]:
        # İki toplu LLM çağrısının süresi loglanır — batch tek yerel model
        # sunucusunda dakikalar sürebilir (bkz. docs/VALIDATION.md); bir isteğin
        # gerçekten ilerlediğini mi yoksa takılı mı kaldığını ayırt etmek için.
        # Çağıran (BatchAnalysisService) bütçeyi zaten uygulayıp kullanıcıyı
        # bilgilendirmiş olabilir; bu durumda burası no-op'tur. Yine de çağrılır ki
        # bu metot doğrudan kullanıldığında da context window koruması olsun.
        fitted_texts, _ = self.fit_batch_budget(texts)
        documents = [
            {"documentId": document_id, "sourceText": text}
            for document_id, text in enumerate(fitted_texts)
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
        # Batch'te düzeltme turu yapmıyoruz: tek bir bozuk ad için 5 CV'lik
        # extraction'ı (dakikalar) tekrarlamak orantısız olurdu. Doğrulanamayan ad
        # None'a çekilir; BatchAnalysisService zaten dosya adına düşer.
        for document_id, item in profiles_by_id.items():
            profile = item.profile
            source_text = fitted_texts[document_id]
            if profile.candidateName is not None and not is_grounded_in_source(
                profile.candidateName, source_text
            ):
                logger.warning(
                    "documentId=%d: candidateName kaynak metinde yok (%r) — None'a çekiliyor",
                    document_id, profile.candidateName,
                )
                profile = profile.model_copy(update={"candidateName": None})
            profile = self._ground_profile_skills(profile, source_text)
            if profile != item.profile:
                profiles_by_id[document_id] = item.model_copy(update={"profile": profile})

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
                            evaluations_by_id[document_id].evaluation.scores,
                            criteria,
                            profiles_by_id[document_id].profile,
                            fitted_texts[document_id],
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
        evaluation: EvaluationResult,
        criteria: list[Criterion],
        profile: CandidateProfile,
        source_text: str,
    ) -> EvaluationResult:
        return evaluation.model_copy(
            update={
                "scores": CVAnalysisService._normalize_scores(
                    evaluation.scores, criteria, profile, source_text
                )
            }
        )

    @staticmethod
    def _normalize_scores(
        scores,
        criteria: list[Criterion],
        profile: CandidateProfile,
        source_text: str,
    ):
        scores_by_id = {score.criterionId: score for score in scores}
        expected_ids = {criterion.id for criterion in criteria}
        if len(scores_by_id) != len(scores) or set(scores_by_id) != expected_ids:
            raise LLMOutputValidationError("Model kriterlerin her biri için tek bir skor üretmedi.")

        profile_content = CVAnalysisService._profile_content(profile)
        invalid_ids = {
            score.criterionId
            for score in scores
            if score.score >= 20 and not any(
                is_grounded_claim_in_source(evidence, profile_content)
                and is_grounded_claim_in_source(evidence, source_text)
                for evidence in score.evidence
            )
        }
        for criterion_id in invalid_ids:
            logger.warning(
                "%s kriterinin kanıtı profile/kaynağa dayanmadı; skor 0'a indirildi",
                criterion_id,
            )

        return [
            scores_by_id[criterion.id].model_copy(update={
                "criterionLabel": criterion.label,
                **(
                    {
                        "score": 0,
                        "evidence": ["Kanıt yok"],
                        "reason": "Kanıt normalize profil ve kaynak belgede doğrulanamadı.",
                    }
                    if criterion.id in invalid_ids
                    else {}
                ),
            })
            for criterion in criteria
        ]

    @staticmethod
    def _profile_content(profile: CandidateProfile) -> str:
        values: list[str] = []

        def collect(value) -> None:
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(profile.model_dump(mode="json"))
        return "\n".join(values)

    async def analyze(
        self, pdf_bytes: bytes, criteria: list[Criterion]
    ) -> tuple[CandidateProfile, EvaluationResult, bool]:
        text, truncated = await self.extract_text(pdf_bytes)
        profile, evaluation = await self.analyze_from_text(text, criteria)
        return profile, evaluation, truncated
