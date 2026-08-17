"""Tekli CV akışı: validate -> extract -> evaluate (RULES.md §3, §5, §6).

extract_text ve analyze_from_text ayrı metotlar: batch_analysis_service önce TÜM
dosyaları doğrulayıp sonra LLM'e geçmek istiyor (fail-fast), bu yüzden PDF
validation'ı ile LLM adımları ayrıştırılabilir olmalı.
"""
from __future__ import annotations

import asyncio

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

        criteria_json = "\n".join(f"- {c.label}: {c.description}" for c in criteria)
        user_prompt = (
            f"CANDIDATE_PROFILE (JSON):\n{profile.model_dump_json()}\n\n"
            f"CRITERIA:\n{criteria_json}\n\n"
            "criterionLabel alanında yukarıdaki kriter etiketlerini birebir kullan."
        )
        evaluation = await self._llm.structured_chat(
            CANDIDATE_EVALUATOR_SYSTEM, user_prompt, EvaluationResult
        )
        return profile, evaluation

    async def analyze(
        self, pdf_bytes: bytes, criteria: list[Criterion]
    ) -> tuple[CandidateProfile, EvaluationResult]:
        text = await self.extract_text(pdf_bytes)
        return await self.analyze_from_text(text, criteria)
