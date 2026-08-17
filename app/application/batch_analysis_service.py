"""Çoklu CV akışı (RULES.md §4, §7, §9).

İki aşamalı hata politikası:
1. Validation aşaması fail-fast'tir: herhangi bir dosya bozuk/şifreli/okunamazsa
   PDF'in "hatalı format tespit ederse süreci kesip net hata döner" şartı gereği
   TÜM batch reddedilir, hiçbir dosya LLM'e gönderilmez.
2. Validation'ı geçen dosyalarda LLM adımı (extraction/evaluation) başarısız olursa
   sadece o dosya sonuçtan çıkarılır, batch'in geri kalanı etkilenmez (bu daha
   öngörülemez bir hata sınıfı olduğu için izole edilir).
"""
from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple

from app.application.cv_analysis_service import CVAnalysisService
from app.domain.errors import AppError, PDFValidationError
from app.domain.models import Criterion, MultiAnalysisResponse, TopCandidate
from app.domain.scoring import compute_average, dynamic_scores_dict, rank_top_n

logger = logging.getLogger(__name__)


class BatchResult(NamedTuple):
    response: MultiAnalysisResponse
    failed: list[tuple[str, str]]  # (dosya adı, kullanıcıya gösterilecek hata mesajı)


class BatchAnalysisService:
    def __init__(self, cv_service: CVAnalysisService, max_concurrency: int = 2):
        self._cv_service = cv_service
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def analyze_batch(
        self, files: list[tuple[str, bytes]], criteria: list[Criterion]
    ) -> BatchResult:
        texts = await self._validate_all_or_abort(files)

        outcomes = await asyncio.gather(
            *(self._analyze_one(name, text, criteria) for name, text in texts)
        )

        candidates: list[TopCandidate] = []
        failed: list[tuple[str, str]] = []
        for (filename, _), outcome in zip(texts, outcomes):
            if isinstance(outcome, AppError):
                failed.append((filename, outcome.user_message))
                continue
            profile, evaluation = outcome
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
            status="success" if candidates else "error",
            processedCVCount=len(candidates),
            userDefinedCriteria=[c.label for c in criteria],
            topCandidates=rank_top_n(candidates, n=3),
        )
        return BatchResult(response=response, failed=failed)

    async def _validate_all_or_abort(
        self, files: list[tuple[str, bytes]]
    ) -> list[tuple[str, str]]:
        """Tüm dosyaları paralel doğrular/metnini çıkarır. Biri bile geçersizse
        tüm batch'i PDFValidationError ile reddeder (LLM'e hiç gönderilmez)."""
        outcomes = await asyncio.gather(
            *(self._safe_extract(name, data) for name, data in files)
        )
        errors = [
            (name, outcome.user_message)
            for (name, _), outcome in zip(files, outcomes)
            if isinstance(outcome, AppError)
        ]
        if errors:
            bad_names = ", ".join(name for name, _ in errors)
            raise PDFValidationError(
                f"Şu dosyalar geçersiz olduğu için toplu analiz başlatılmadı: {bad_names}. "
                "Sorunlu dosyaları çıkarıp tekrar gönderin."
            )
        return [(name, text) for (name, _), text in zip(files, outcomes)]

    async def _safe_extract(self, filename: str, data: bytes) -> str | AppError:
        try:
            return await self._cv_service.extract_text(data)
        except AppError as exc:
            logger.info("PDF validation başarısız (%s): %s", filename, exc.user_message)
            return exc

    async def _analyze_one(self, filename: str, text: str, criteria: list[Criterion]):
        async with self._semaphore:
            try:
                return await self._cv_service.analyze_from_text(text, criteria)
            except AppError as exc:
                logger.info("CV işlenemedi (%s): %s", filename, exc.user_message)
                return exc
