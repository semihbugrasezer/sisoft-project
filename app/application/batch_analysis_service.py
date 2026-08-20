"""Çoklu CV akışı (README.md → Çoklu CV Skorlama ve Sıralama).

İki aşamalı hata politikası:
1. Validation aşaması fail-fast'tir: herhangi bir dosya bozuk/şifreli/okunamazsa
   PDF'in "hatalı format tespit ederse süreci kesip net hata döner" şartı gereği
   TÜM batch reddedilir, hiçbir dosya LLM'e gönderilmez.
2. Doğrulanan metinler tek batch çağrısında ortak profillere çevrilir; ikinci batch
   çağrısı yalnız bu profilleri değerlendirir. Her CV skorlanamazsa eksik sıralama
   dönmek yerine tüm analiz kontrollü hatayla kesilir.
"""
from __future__ import annotations

import asyncio

from app.application.cv_analysis_service import CVAnalysisService
from app.domain.errors import AppError, PDFValidationError
from app.domain.models import MAX_CV_COUNT, Criterion, MultiAnalysisResponse, TopCandidate
from app.domain.scoring import compute_average, dynamic_scores_dict, rank_top_n

class BatchAnalysisService:
    def __init__(self, cv_service: CVAnalysisService):
        self._cv_service = cv_service

    async def analyze_batch(
        self, files: list[tuple[str, bytes]], criteria: list[Criterion]
    ) -> tuple[MultiAnalysisResponse, list[str]]:
        """İkinci dönüş değeri: 20k karakter sınırı nedeniyle kırpılan dosya adları
        (boşsa hiçbiri kırpılmadı) — JSON çıktı şeması sabit olduğu için (ödev
        sözleşmesi, `extra="forbid"`) bu bilgiyi oraya eklemek yerine ayrı döneriz;
        handlers.py bunu kullanıcıya JSON'dan önce ayrı bir mesajla bildirir."""
        if len(files) > MAX_CV_COUNT:
            raise PDFValidationError(f"En fazla {MAX_CV_COUNT} CV yükleyebilirsiniz.")
        texts = await self._validate_all_or_abort(files)
        truncated_files = [name for name, _, truncated in texts if truncated]
        analyses = await self._cv_service.analyze_batch_from_texts(
            [text for _, text, _ in texts], criteria
        )

        candidates: list[TopCandidate] = []
        for (filename, _, _), (profile, evaluation) in zip(texts, analyses):
            candidates.append(
                TopCandidate(
                    rank=0,  # rank_top_n atayacak
                    candidateName=profile.candidateName or filename,
                    pdfFileName=filename,
                    dynamicScores=dynamic_scores_dict(evaluation.scores),
                    averageScore=compute_average(evaluation.scores),
                    hrEvaluation=evaluation.hrEvaluation,
                )
            )

        response = MultiAnalysisResponse(
            status="success",
            processedCVCount=len(candidates),
            userDefinedCriteria=[c.label for c in criteria],
            topCandidates=rank_top_n(candidates, n=3),
        )
        return response, truncated_files

    async def _validate_all_or_abort(
        self, files: list[tuple[str, bytes]]
    ) -> list[tuple[str, str, bool]]:
        """Tüm dosyaları paralel doğrular/metnini çıkarır. Biri bile geçersizse
        tüm batch'i PDFValidationError ile reddeder (LLM'e hiç gönderilmez)."""
        outcomes = await asyncio.gather(
            *(self._cv_service.extract_text(data) for _, data in files),
            return_exceptions=True,
        )
        errors: list[str] = []
        for (name, _), outcome in zip(files, outcomes):
            if isinstance(outcome, AppError):
                errors.append(name)
            elif isinstance(outcome, BaseException):
                raise outcome
        if errors:
            bad_names = ", ".join(errors)
            raise PDFValidationError(
                f"Şu dosyalar geçersiz olduğu için toplu analiz başlatılmadı: {bad_names}. "
                "Sorunlu dosyaları çıkarıp tekrar gönderin."
            )
        return [(name, text, truncated) for (name, _), (text, truncated) in zip(files, outcomes)]
