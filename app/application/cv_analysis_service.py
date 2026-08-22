"""Tekli ve batch CV akışı: validate -> extract -> evaluate (docs/LLM_PIPELINE.md).

extract_text ve analyze_from_text ayrı metotlar: batch_analysis_service önce TÜM
dosyaları doğrulayıp sonra LLM'e geçmek istiyor (all-or-nothing ön doğrulama),
bu yüzden PDF validation'ı ile LLM adımları ayrıştırılabilir olmalı. Batch yolu
normalde tüm profilleri tek extraction çağrısında, tüm skorları yalnız normalize
profillerden ikinci çağrıda üretir; eksik/tekrarlı evaluation belgeleri tekli
şemayla tamamlanır.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import Counter
from typing import Literal, cast

from app.domain.errors import LLMOutputValidationError
from app.domain.grounding import (
    find_criterion_passages,
    has_criterion_term,
    has_explicit_negation,
    is_grounded_in_source,
    locate_quote,
    make_evidence_id,
)
from app.domain.models import (
    BatchCandidateEvaluation,
    BatchEvaluationResult,
    BatchProfileResult,
    CandidateProfile,
    Criterion,
    CriterionEvidence,
    CriterionEvidenceDraft,
    EvaluationResult,
    EvidenceExtractionResult,
    EvidenceRecord,
    EvidenceVerificationResult,
    GroundedCandidate,
    GroundedCriterionEvidence,
    NormalizedCandidate,
    NormalizedCandidateDraft,
    VerifiedEvidence,
)
from app.domain.ports import LLMPort
from app.infrastructure.llm.prompts import (
    CANDIDATE_EVALUATOR_SYSTEM,
    CV_EXTRACTOR_SYSTEM,
    EVIDENCE_VERIFIER_SYSTEM,
)
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
        draft = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM,
            self._extraction_prompt(text, criteria),
            NormalizedCandidateDraft,
        )
        profile = await self._ground_candidate_name(draft.profile, text, criteria)
        draft = draft.model_copy(update={"profile": profile})
        draft = await self._ground_profile_with_retry(draft, text, criteria)
        draft = await self._complete_missing_evidence(draft, text, criteria)
        grounded_candidate = self._ground_evidence(draft, text, criteria, document_id=0)
        candidate = (await self._verify_candidates([grounded_candidate], criteria))[0]

        evaluation = await self._evaluate_candidate(candidate, criteria)
        return candidate.profile, evaluation

    @staticmethod
    def _extraction_prompt(source_text: str, criteria: list[Criterion]) -> str:
        criteria_data = [criterion.model_dump(mode="json") for criterion in criteria]
        return (
            f"SOURCE_TEXT:\n{source_text}\n\nCRITERIA (JSON):\n"
            + json.dumps(criteria_data, ensure_ascii=False)
        )

    async def _ground_candidate_name(
        self,
        profile: CandidateProfile,
        source_text: str,
        criteria: list[Criterion],
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
            self._extraction_prompt(source_text, criteria),
            NormalizedCandidateDraft,
        )
        if is_grounded_in_source(retried.profile.candidateName, source_text):
            return profile.model_copy(update={"candidateName": retried.profile.candidateName})

        logger.warning(
            "candidateName ikinci denemede de doğrulanamadı (%r) — None'a çekiliyor",
            retried.profile.candidateName,
        )
        return profile.model_copy(update={"candidateName": None})

    @staticmethod
    def _ground_profile(
        profile: CandidateProfile,
        source_text: str,
    ) -> CandidateProfile:
        def grounded(value: str | None) -> str | None:
            return value if value is None or is_grounded_in_source(value, source_text) else None

        contact = profile.contact.model_copy(update={
            field: grounded(getattr(profile.contact, field))
            for field in ("email", "phone", "location")
        })
        skills = [
            skill for skill in profile.skills
            if is_grounded_in_source(skill, source_text)
        ]
        work_experiences = []
        for work_item in profile.workExperiences:
            values = {
                field: grounded(getattr(work_item, field))
                for field in ("company", "title", "startDate", "endDate", "description")
            }
            if any(values.values()):
                work_experiences.append(work_item.model_copy(update=values))
        education = []
        for education_item in profile.education:
            values = {
                field: grounded(getattr(education_item, field))
                for field in ("institution", "degree", "field", "graduationDate")
            }
            if any(values.values()):
                education.append(education_item.model_copy(update=values))
        languages = [
            language.model_copy(update={"level": grounded(language.level)})
            for language in profile.languages
            if is_grounded_in_source(language.name, source_text)
        ]
        normalized = profile.model_copy(update={
            "contact": contact,
            "summary": grounded(profile.summary),
            "skills": skills,
            "workExperiences": work_experiences,
            "education": education,
            "languages": languages,
        })
        if profile != normalized:
            logger.warning("Kaynağa dayanmayan profil alanları normalize JSON'dan çıkarıldı")
        return normalized

    async def _ground_profile_with_retry(
        self,
        draft: NormalizedCandidateDraft,
        source_text: str,
        criteria: list[Criterion],
    ) -> NormalizedCandidateDraft:
        normalized = self._ground_profile(draft.profile, source_text)
        if (
            draft.profile == normalized
            and not self._has_missing_source_section(draft.profile, source_text)
        ):
            return draft.model_copy(update={"profile": normalized})

        logger.warning("Profil grounding/tamlık kontrolü başarısız; tek düzeltme turu deneniyor")
        retried = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM
            + " DÜZELTME: Tüm dolu profil değerlerini SOURCE_TEXT içinden birebir kopyala."
            " Özellikle summary alanını yeniden yazma; kısa bir kaynak alıntısı kullan.",
            self._extraction_prompt(source_text, criteria),
            NormalizedCandidateDraft,
        )
        # Aday adı bir önceki özel kontrolün sonucudur; genel alan düzeltmesi bu
        # doğrulanmış değeri değiştiremez.
        retried_profile = retried.profile.model_copy(
            update={"candidateName": draft.profile.candidateName}
        )
        return retried.model_copy(
            update={"profile": self._ground_profile(retried_profile, source_text)}
        )

    @staticmethod
    def _ground_evidence(
        draft: NormalizedCandidateDraft,
        source_text: str,
        criteria: list[Criterion],
        document_id: int,
    ) -> GroundedCandidate:
        draft_by_id = {
            item.criterionId: item
            for item in draft.criterionEvidence
            if item.criterionId in {criterion.id for criterion in criteria}
        }
        ledger = []
        for criterion in criteria:
            grounded_items = []
            item = draft_by_id.get(criterion.id)
            seen_quotes = set()
            quotes = [] if item is None else [draft.quote for draft in item.items]
            used_fallback = not quotes
            if used_fallback:
                quotes = find_criterion_passages(
                    source_text,
                    [criterion.label, *criterion.evidenceHints],
                )
            while True:
                for quote in quotes:
                    if quote in seen_quotes:
                        continue
                    seen_quotes.add(quote)
                    span = locate_quote(source_text, quote)
                    if span is None:
                        continue
                    start, end = span
                    grounded_items.append(EvidenceRecord(
                        evidenceId=make_evidence_id(
                            document_id, criterion.id, start, end, source_text[start:end]
                        ),
                        quote=source_text[start:end],
                        start=start,
                        end=end,
                    ))
                if grounded_items or used_fallback:
                    break
                quotes = find_criterion_passages(
                    source_text,
                    [criterion.label, *criterion.evidenceHints],
                )
                used_fallback = True
            ledger.append(GroundedCriterionEvidence(
                criterionId=criterion.id,
                items=grounded_items,
            ))
        return GroundedCandidate(profile=draft.profile, criterionEvidence=ledger)

    async def _complete_missing_evidence(
        self,
        draft: NormalizedCandidateDraft,
        source_text: str,
        criteria: list[Criterion],
    ) -> NormalizedCandidateDraft:
        existing = {item.criterionId: item for item in draft.criterionEvidence}
        missing = [
            criterion for criterion in criteria
            if not existing.get(criterion.id) or not existing[criterion.id].items
        ]
        if not missing:
            return draft

        repaired = {}
        for criterion in missing:
            evidence = await self._request_evidence_repair(source_text, criterion)
            repaired[criterion.id] = evidence
        return draft.model_copy(update={
            "criterionEvidence": [
                existing.get(criterion.id)
                if existing.get(criterion.id) and existing[criterion.id].items
                else repaired.get(
                    criterion.id,
                    existing.get(criterion.id)
                    or CriterionEvidenceDraft(criterionId=criterion.id),
                )
                for criterion in criteria
            ]
        })

    async def _verify_candidates(
        self,
        candidates: list[GroundedCandidate],
        criteria: list[Criterion],
    ) -> list[NormalizedCandidate]:
        criteria_by_id = {criterion.id: criterion for criterion in criteria}
        records = [
            {
                "evidenceId": evidence.evidenceId,
                "criterion": criteria_by_id[criterion_evidence.criterionId].model_dump(
                    mode="json"
                ),
                "exactQuote": evidence.quote,
            }
            for candidate in candidates
            for criterion_evidence in candidate.criterionEvidence
            for evidence in criterion_evidence.items
        ]
        if not records:
            return [
                NormalizedCandidate(
                    profile=candidate.profile,
                    criterionEvidence=[
                        CriterionEvidence(criterionId=item.criterionId, items=[])
                        for item in candidate.criterionEvidence
                    ],
                )
                for candidate in candidates
            ]

        prompt = "EVIDENCE_RECORDS (JSON):\n" + json.dumps(records, ensure_ascii=False)
        result = await self._llm.structured_chat(
            EVIDENCE_VERIFIER_SYSTEM,
            prompt,
            EvidenceVerificationResult,
        )
        expected_ids = {
            evidence.evidenceId
            for candidate in candidates
            for item in candidate.criterionEvidence
            for evidence in item.items
        }
        verdicts = self._validated_verdicts(result, expected_ids)
        if verdicts is None:
            logger.warning("Evidence verdict kümesi geçersiz; tek retry deneniyor")
            result = await self._llm.structured_chat(
                EVIDENCE_VERIFIER_SYSTEM,
                prompt + "\n\nDÜZELTME: Her evidenceId için tam bir kez verdict üret.",
                EvidenceVerificationResult,
            )
            verdicts = self._validated_verdicts(result, expected_ids)
        if verdicts is None:
            logger.warning("Evidence verifier iki kez geçersiz çıktı; tüm kanıtlar kapatıldı")
            verdicts = {}

        criteria_by_id = {criterion.id: criterion for criterion in criteria}
        for candidate in candidates:
            for item in candidate.criterionEvidence:
                criterion = criteria_by_id[item.criterionId]
                criterion_texts = [criterion.label, *criterion.evidenceHints]
                for evidence in item.items:
                    verdict = verdicts.get(evidence.evidenceId)
                    has_term = has_criterion_term(evidence.quote, criterion_texts)
                    has_negation = has_explicit_negation(evidence.quote)
                    if has_term and has_negation:
                        verdicts[evidence.evidenceId] = "contradicts"
                    elif has_term and verdict in {"contradicts", "irrelevant"}:
                        verdicts[evidence.evidenceId] = "supports"
                    elif verdict == "contradicts":
                        verdicts[evidence.evidenceId] = "irrelevant"

        return [
            NormalizedCandidate(
                profile=candidate.profile,
                criterionEvidence=[
                    CriterionEvidence(
                        criterionId=item.criterionId,
                        items=[
                            VerifiedEvidence(
                                **evidence.model_dump(),
                                relation=cast(
                                    Literal["supports", "contradicts"],
                                    verdicts[evidence.evidenceId],
                                ),
                            )
                            for evidence in item.items
                            if verdicts.get(evidence.evidenceId) in {"supports", "contradicts"}
                        ],
                    )
                    for item in candidate.criterionEvidence
                ],
            )
            for candidate in candidates
        ]

    @staticmethod
    def _validated_verdicts(result, expected_ids: set[str]) -> dict[str, str] | None:
        ids = [verdict.evidenceId for verdict in result.verdicts]
        if len(ids) != len(set(ids)) or set(ids) != expected_ids:
            return None
        return {verdict.evidenceId: verdict.verdict for verdict in result.verdicts}

    @staticmethod
    def _has_missing_source_section(profile: CandidateProfile, source_text: str) -> bool:
        expected_sections = (
            (profile.summary, r"(?:özet|ozet|summary|hakkımda|hakkimda)"),
            (profile.skills, r"(?:yetenekler|beceriler|skills|teknolojiler)"),
            (profile.workExperiences, r"(?:iş deneyimi|is deneyimi|experience|employment)"),
            (profile.education, r"(?:eğitim|egitim|education)"),
            (profile.languages, r"(?:diller|languages)"),
        )
        normalized_source = source_text.casefold()
        return any(
            not value and re.search(rf"(?m)^\s*{heading}\b", normalized_source)
            for value, heading in expected_sections
        )

    async def _evaluate_candidate(
        self,
        candidate: NormalizedCandidate,
        criteria: list[Criterion],
    ) -> EvaluationResult:
        criteria_text = "\n".join(
            f"- id={criterion.id}; label={criterion.label}; "
            f"description={criterion.description}; "
            f"evidenceHints={', '.join(criterion.evidenceHints) or 'yok'}"
            for criterion in criteria
        )
        user_prompt = (
            f"NORMALIZED_CANDIDATE (JSON):\n{candidate.model_dump_json()}\n\n"
            "CRITERIA:\n"
            + criteria_text
            + "\n\ncriterionId ve criterionLabel alanlarında yukarıdaki değerleri birebir kullan."
        )
        evaluation = await self._llm.structured_chat(
            CANDIDATE_EVALUATOR_SYSTEM, user_prompt, EvaluationResult
        )
        try:
            normalized = self._normalize_evaluation(evaluation, criteria, candidate)
        except LLMOutputValidationError:
            logger.warning("Evaluation kriter kümesi eksik/tekrarlı; tek retry deneniyor")
            evaluation = await self._llm.structured_chat(
                CANDIDATE_EVALUATOR_SYSTEM,
                user_prompt
                + "\n\nDÜZELTME: Her CRITERIA öğesi için tam bir kez skor üret; "
                "kriter atlama, ekleme veya tekrar yapma.",
                EvaluationResult,
            )
            return self._normalize_evaluation(evaluation, criteria, candidate)
        if not self._scores_changed(evaluation.scores, normalized.scores):
            return normalized

        logger.warning("Evaluation evidenceId bağlaması geçersiz; tek retry deneniyor")
        evaluation = await self._llm.structured_chat(
            CANDIDATE_EVALUATOR_SYSTEM,
            user_prompt
            + "\n\nDÜZELTME: evidenceIds değerlerini NORMALIZED_CANDIDATE içinde aynı "
            "criterionId altında bulunan ID'lerden birebir kopyala. 20+ skor için en az "
            "bir supports ID zorunludur; supports yoksa 0-19 ver.",
            EvaluationResult,
        )
        return self._normalize_evaluation(evaluation, criteria, candidate)

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
        # Üç toplu LLM çağrısının süresi loglanır — batch tek yerel model
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
        criteria_data = [criterion.model_dump(mode="json") for criterion in criteria]
        logger.info("Batch extraction başlıyor (%d belge)", len(texts))
        t0 = time.monotonic()
        profiles_result = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM
            + " Birden fazla belge verildiğinde her documentId için tam fakat öz bir profil üret.",
            "DOCUMENTS (JSON):\n"
            + json.dumps(documents, ensure_ascii=False)
            + "\n\nCRITERIA (JSON):\n"
            + json.dumps(criteria_data, ensure_ascii=False),
            BatchProfileResult,
        )
        logger.info("Batch extraction bitti (%.1fs)", time.monotonic() - t0)
        profiles_by_id = self._items_by_document_id(
            profiles_result.candidates, len(texts)
        )
        profiles_by_id = await self._complete_batch_missing_evidence(
            profiles_by_id, fitted_texts, criteria
        )
        # Batch'te düzeltme turu yapmıyoruz: tek bir bozuk ad için 5 CV'lik
        # extraction'ı (dakikalar) tekrarlamak orantısız olurdu. Doğrulanamayan ad
        # None'a çekilir; BatchAnalysisService zaten dosya adına düşer.
        for document_id, item in profiles_by_id.items():
            draft = item.candidate
            profile = draft.profile
            source_text = fitted_texts[document_id]
            if profile.candidateName is not None and not is_grounded_in_source(
                profile.candidateName, source_text
            ):
                logger.warning(
                    "documentId=%d: candidateName kaynak metinde yok (%r) — None'a çekiliyor",
                    document_id, profile.candidateName,
                )
                profile = profile.model_copy(update={"candidateName": None})
            draft = draft.model_copy(
                update={"profile": self._ground_profile(profile, source_text)}
            )
            profiles_by_id[document_id] = item.model_copy(update={"candidate": draft})

        grounded_candidates = [
            self._ground_evidence(
                profiles_by_id[document_id].candidate,
                fitted_texts[document_id],
                criteria,
                document_id,
            )
            for document_id in range(len(texts))
        ]
        verified_candidates = await self._verify_candidates(grounded_candidates, criteria)

        normalized_profiles = [
            {
                "documentId": document_id,
                "candidate": verified_candidates[document_id].model_dump(mode="json"),
            }
            for document_id in range(len(texts))
        ]
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
        id_counts = Counter(item.documentId for item in evaluations_result.candidates)
        expected_ids = set(range(len(texts)))
        evaluations_by_id = {
            item.documentId: item.evaluation
            for item in evaluations_result.candidates
            if item.documentId in expected_ids and id_counts[item.documentId] == 1
        }
        for document_id, evaluation in list(evaluations_by_id.items()):
            try:
                scores = self._normalize_scores(
                    evaluation.scores,
                    criteria,
                    verified_candidates[document_id],
                )
            except LLMOutputValidationError:
                del evaluations_by_id[document_id]
            else:
                update = {"scores": scores}
                if self._scores_changed(evaluation.scores, scores):
                    del evaluations_by_id[document_id]
                else:
                    evaluations_by_id[document_id] = evaluation.model_copy(update=update)
        for document_id in sorted(expected_ids - set(evaluations_by_id)):
            logger.warning(
                "Batch evaluation documentId=%d için eksik/tekrarlı; tekli retry deneniyor",
                document_id,
            )
            retry = await self._evaluate_candidate(
                verified_candidates[document_id],
                criteria,
            )
            evaluations_by_id[document_id] = BatchCandidateEvaluation(
                scores=retry.scores,
                hrEvaluation=retry.hrEvaluation,
            )

        return [
            (
                verified_candidates[document_id].profile,
                evaluations_by_id[document_id],
            )
            for document_id in range(len(texts))
        ]

    async def _complete_batch_missing_evidence(
        self,
        profiles_by_id,
        source_texts: list[str],
        criteria: list[Criterion],
    ):
        missing_document_ids: dict[str, list[int]] = {
            criterion.id: [] for criterion in criteria
        }
        for document_id, item in profiles_by_id.items():
            existing = {
                evidence.criterionId: evidence
                for evidence in item.candidate.criterionEvidence
            }
            missing = [
                criterion
                for criterion in criteria
                if not existing.get(criterion.id) or not existing[criterion.id].items
            ]
            for criterion in missing:
                missing_document_ids[criterion.id].append(document_id)
        if not any(missing_document_ids.values()):
            return profiles_by_id

        repair_tasks = [
            (document_id, criterion)
            for criterion in criteria
            for document_id in missing_document_ids[criterion.id]
        ]
        repair_results = await asyncio.gather(*(
            self._request_evidence_repair(source_texts[document_id], criterion)
            for document_id, criterion in repair_tasks
        ))
        repaired_items = {
            (document_id, criterion.id): evidence
            for (document_id, criterion), evidence in zip(
                repair_tasks, repair_results, strict=True
            )
        }

        for document_id in profiles_by_id:
            batch_item = profiles_by_id[document_id]
            existing = {
                item.criterionId: item
                for item in batch_item.candidate.criterionEvidence
            }
            repaired = {
                criterion_id: evidence
                for (candidate_id, criterion_id), evidence in repaired_items.items()
                if candidate_id == document_id
            }
            merged = [
                existing.get(criterion.id)
                if existing.get(criterion.id) and existing[criterion.id].items
                else repaired.get(
                    criterion.id,
                    existing.get(criterion.id)
                    or CriterionEvidenceDraft(criterionId=criterion.id),
                )
                for criterion in criteria
            ]
            profiles_by_id[document_id] = batch_item.model_copy(update={
                "candidate": batch_item.candidate.model_copy(update={
                    "criterionEvidence": merged
                })
            })
        return profiles_by_id

    async def _request_evidence_repair(
        self, source_text: str, criterion: Criterion
    ) -> CriterionEvidenceDraft:
        result = await self._llm.structured_chat(
            CV_EXTRACTOR_SYSTEM
            + " DÜZELTME TURU: Profile üretme. Yalnız verilen tek CRITERION için "
            "criterionEvidence döndür; sınırlı/negatif kanıtı atlama.",
            self._extraction_prompt(source_text, [criterion]),
            EvidenceExtractionResult,
        )
        matching = [
            item for item in result.criterionEvidence
            if item.criterionId == criterion.id
        ]
        if len(matching) != 1:
            logger.warning("Evidence repair criterionId kümesi geçersiz; boş kabul edildi")
            return CriterionEvidenceDraft(criterionId=criterion.id)
        return matching[0]

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
        candidate: NormalizedCandidate,
    ) -> EvaluationResult:
        scores = CVAnalysisService._normalize_scores(
            evaluation.scores, criteria, candidate
        )
        update = {"scores": scores}
        if CVAnalysisService._scores_changed(evaluation.scores, scores):
            update.update(CVAnalysisService._final_report_fields(scores))
        return evaluation.model_copy(update=update)

    @staticmethod
    def _normalize_scores(
        scores,
        criteria: list[Criterion],
        candidate: NormalizedCandidate,
    ):
        scores_by_id = {score.criterionId: score for score in scores}
        expected_ids = {criterion.id for criterion in criteria}
        if len(scores_by_id) != len(scores) or set(scores_by_id) != expected_ids:
            raise LLMOutputValidationError("Model kriterlerin her biri için tek bir skor üretmedi.")

        support_ids_by_criterion = {
            item.criterionId: {
                evidence.evidenceId
                for evidence in item.items
                if evidence.relation == "supports"
            }
            for item in candidate.criterionEvidence
        }
        all_ids_by_criterion = {
            item.criterionId: {evidence.evidenceId for evidence in item.items}
            for item in candidate.criterionEvidence
        }
        invalid_ids = set()
        valid_evidence_by_id: dict[str, list[str]] = {}
        for score in scores:
            deduplicated_ids = list(dict.fromkeys(score.evidenceIds))
            valid_evidence = [
                evidence_id
                for evidence_id in deduplicated_ids
                if evidence_id in all_ids_by_criterion.get(score.criterionId, set())
            ]
            valid_evidence_by_id[score.criterionId] = valid_evidence
            used_support = set(valid_evidence) & support_ids_by_criterion.get(
                score.criterionId, set()
            )
            has_unknown_or_duplicate = (
                len(deduplicated_ids) != len(score.evidenceIds)
                or len(valid_evidence) != len(deduplicated_ids)
            )
            high_score_uses_non_support = (
                score.score >= 20 and set(valid_evidence) != used_support
            )
            if (
                has_unknown_or_duplicate
                or (score.score >= 20 and not used_support)
                or high_score_uses_non_support
            ):
                invalid_ids.add(score.criterionId)
        for criterion_id in invalid_ids:
            logger.warning(
                "%s kriterinin evidenceId değeri doğrulanmış destek kanıtına bağlı değil; "
                "skor 0'a indirildi",
                criterion_id,
            )

        return [
            scores_by_id[criterion.id].model_copy(update={
                "criterionLabel": criterion.label,
                **(
                    {
                        "score": 0,
                        "evidenceIds": [],
                        "reason": "Bu kriter için doğrulanmış destekleyici kanıt bulunamadı.",
                    }
                    if criterion.id in invalid_ids
                    else (
                        {"evidenceIds": valid_evidence_by_id[criterion.id]}
                        if scores_by_id[criterion.id].evidenceIds else {}
                    )
                ),
            })
            for criterion in criteria
        ]

    @staticmethod
    def _scores_changed(original, normalized) -> bool:
        original_by_id = {score.criterionId: score.score for score in original}
        return any(original_by_id.get(score.criterionId) != score.score for score in normalized)

    @staticmethod
    def _final_hr_evaluation(scores) -> str:
        rendered = "; ".join(
            f"{score.criterionLabel} {score.score}/100" for score in scores
        )
        return f"Doğrulanmış kriter skorları: {rendered}."

    @staticmethod
    def _final_report_fields(scores) -> dict[str, object]:
        strengths = [
            f"{score.criterionLabel}: doğrulanmış güçlü uyum ({score.score}/100)."
            for score in scores
            if score.score >= 60
        ] or ["Doğrulanmış kriter skorlarına göre güçlü yön tespit edilmedi."]
        weaknesses = [
            f"{score.criterionLabel}: doğrulanmış kanıt yetersiz ({score.score}/100)."
            for score in scores
            if score.score < 40
        ] or ["Doğrulanmış kriter skorlarına göre belirgin bir zayıf yön tespit edilmedi."]
        recommendations = [
            f"{score.criterionLabel} kriterini destekleyen somut CV kanıtı eklenebilir."
            for score in scores
            if score.score < 40
        ] or ["Mevcut kriterler kapsamında özel bir gelişim ihtiyacı tespit edilmedi."]
        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "hrEvaluation": CVAnalysisService._final_hr_evaluation(scores),
        }

    async def analyze(
        self, pdf_bytes: bytes, criteria: list[Criterion]
    ) -> tuple[CandidateProfile, EvaluationResult, bool]:
        text, truncated = await self.extract_text(pdf_bytes)
        profile, evaluation = await self.analyze_from_text(text, criteria)
        return profile, evaluation, truncated
