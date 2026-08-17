"""Tekli CV akışı: validate -> extract -> evaluate (RULES.md §3, §5, §6).

extract_text ve analyze_from_text ayrı metotlar: batch_analysis_service önce TÜM
dosyaları doğrulayıp sonra LLM'e geçmek istiyor (fail-fast), bu yüzden PDF
validation'ı ile LLM adımları ayrıştırılabilir olmalı.
"""
from __future__ import annotations

import asyncio

from app.domain.errors import LLMOutputValidationError
from app.domain.models import CandidateProfile, Criterion, EvaluationResult
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.prompts import CANDIDATE_EVALUATOR_SYSTEM, CV_EXTRACTOR_SYSTEM
from app.infrastructure.pdf.pymupdf_parser import validate_and_extract_text


class CVAnalysisService:
    def __init__(self, llm: OllamaClient):
        self._llm = llm

    async def extract_text(self, pdf_bytes: bytes) -> str:
        # Blocking PDF işi event loop'u bloklamasın diye thread'e atılır.
        return await asyncio.to_thread(validate_and_extract_text, pdf_bytes)

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

        scores_by_id = {score.criterionId: score for score in evaluation.scores}
        expected_ids = {criterion.id for criterion in criteria}
        if len(scores_by_id) != len(evaluation.scores) or set(scores_by_id) != expected_ids:
            raise LLMOutputValidationError("Model kriterlerin her biri için tek bir skor üretmedi.")

        normalized_scores = [
            scores_by_id[criterion.id].model_copy(
                update={"criterionLabel": criterion.label}
            )
            for criterion in criteria
        ]
        return profile, evaluation.model_copy(update={"scores": normalized_scores})

    async def analyze(
        self, pdf_bytes: bytes, criteria: list[Criterion]
    ) -> tuple[CandidateProfile, EvaluationResult]:
        text = await self.extract_text(pdf_bytes)
        return await self.analyze_from_text(text, criteria)
