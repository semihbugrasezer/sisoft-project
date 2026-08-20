"""Çoklu CV akışı (docs/CONCURRENCY.md).

İki aşamalı hata politikası:
1. Validation aşaması all-or-nothing'dir: TÜM dosyalar önce paralel doğrulanır
   (asyncio.gather), sonra herhangi biri bozuk/şifreli/okunamazsa
   PDF'in "hatalı format tespit ederse süreci kesip net hata döner" şartı gereği
   TÜM batch reddedilir, hiçbir dosya LLM'e gönderilmez.
2. Doğrulanan metinler tek batch çağrısında ortak profillere çevrilir; ikinci batch
   çağrısı yalnız bu profilleri değerlendirir. Her CV skorlanamazsa eksik sıralama
   dönmek yerine tüm analiz kontrollü hatayla kesilir.
"""
from __future__ import annotations

import asyncio
import logging
from typing import cast

from app.application.cv_analysis_service import CVAnalysisService
from app.domain.errors import AppError, PDFValidationError
from app.domain.models import MAX_CV_COUNT, Criterion, MultiAnalysisResponse, TopCandidate
from app.domain.scoring import compute_average, dynamic_scores_dict, rank_top_n

logger = logging.getLogger(__name__)


class BatchAnalysisService:
    def __init__(self, cv_service: CVAnalysisService):
        self._cv_service = cv_service

    async def analyze_batch(
        self, files: list[tuple[str, bytes]], criteria: list[Criterion]
    ) -> tuple[MultiAnalysisResponse, list[str]]:
        """İkinci dönüş değeri: metni kırpılan dosya adları (boşsa hiçbiri
        kırpılmadı) — JSON çıktı şeması sabit olduğu için (ödev sözleşmesi,
        `extra="forbid"`) bu bilgiyi oraya eklemek yerine ayrı döneriz;
        handlers.py bunu kullanıcıya JSON'dan önce ayrı bir mesajla bildirir.

        Kırpma İKİ ayrı yerde olabilir ve ikisi de bildirilmelidir:
        1. Dosya başına `MAX_EXTRACTED_CHARS` (20k) — extract_text sırasında.
        2. Batch geneli `MAX_BATCH_EXTRACTED_CHARS` (60k) — hiçbir dosya tek
           başına 20k'yı aşmasa bile tetiklenebilir (ör. 5×15k = 75k)."""
        if len(files) > MAX_CV_COUNT:
            raise PDFValidationError(f"En fazla {MAX_CV_COUNT} CV yükleyebilirsiniz.")
        texts = await self._validate_all_or_abort(files)
        truncated_names = {name for name, _, truncated in texts if truncated}

        # Batch bütçesi burada uygulanır (dosya adları burada bilinir), böylece
        # batch seviyesinde kırpılan dosyalar da kullanıcıya bildirilebilir.
        fitted_texts, batch_trimmed = CVAnalysisService.fit_batch_budget(
            [text for _, text, _ in texts]
        )
        truncated_names.update(texts[index][0] for index in batch_trimmed)
        # Dosya sırasını koru (küme sırası belirsizdir).
        truncated_files = [name for name, _, _ in texts if name in truncated_names]

        analyses = await self._cv_service.analyze_batch_from_texts(fitted_texts, criteria)

        candidates: list[TopCandidate] = []
        for (filename, _, _), (profile, evaluation) in zip(texts, analyses, strict=True):
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
        logger.info("PDF validation başlıyor (%d dosya)", len(files))
        outcomes = await asyncio.gather(
            *(self._cv_service.extract_text(data) for _, data in files),
            return_exceptions=True,
        )
        logger.info("PDF validation bitti")
        errors: list[str] = []
        for (name, _), outcome in zip(files, outcomes, strict=True):
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
        # Yukarıdaki döngü her BaseException'ı ya `errors`'a topladı (sonra fonksiyon
        # PDFValidationError ile döndü) ya da yeniden fırlattı — bu satıra ulaşıldığında
        # outcomes içinde artık yalnızca (text, truncated) tuple'ları vardır. mypy bunu
        # akış analiziyle çıkaramıyor (bkz. cast).
        successful = cast(list[tuple[str, bool]], outcomes)
        return [
            (name, text, truncated)
            for (name, _), (text, truncated) in zip(files, successful, strict=True)
        ]
