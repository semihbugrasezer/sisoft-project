"""BatchAnalysisService'in validation, limit ve top-3 sözleşmesi."""
import pytest

from app.application.batch_analysis_service import BatchAnalysisService
from app.domain.errors import LLMOutputValidationError, PDFValidationError
from app.domain.models import (
    MAX_CV_COUNT,
    CandidateProfile,
    Criterion,
    CriterionScore,
    EvaluationResult,
)

CRITERIA = [Criterion(id="react", label="React", description="React deneyimi")]


class FakeCVService:
    """dosya adı -> davranış eşlemesiyle çalışan sahte servis."""

    def __init__(self, behaviors: dict[str, str]):
        self.behaviors = behaviors  # filename -> "ok" | "invalid_pdf" | "llm_fail"

    async def extract_text(self, pdf_bytes: bytes) -> str:
        filename = pdf_bytes.decode()
        if self.behaviors[filename] == "invalid_pdf":
            raise PDFValidationError(f"{filename} bozuk.")
        return f"text-of-{filename}"

    async def analyze_batch_from_texts(self, texts: list[str], criteria):
        filenames = [text.replace("text-of-", "") for text in texts]
        if any(self.behaviors[filename] == "llm_fail" for filename in filenames):
            raise LLMOutputValidationError("şema hatası")
        return [
            (
                CandidateProfile(
                    candidateName=filename,
                    contact={},
                    summary=None,
                    skills=[],
                    workExperiences=[],
                    education=[],
                    languages=[],
                ),
                EvaluationResult(
                    scores=[
                        CriterionScore(
                            criterionId="react",
                            criterionLabel="React",
                            score=80,
                            evidence=["x"],
                            reason="x",
                        )
                    ],
                    strengths=["x"],
                    weaknesses=[],
                    recommendations=[],
                    hrEvaluation="iyi",
                ),
            )
            for filename in filenames
        ]


def _files(names: list[str]) -> list[tuple[str, bytes]]:
    return [(n, n.encode()) for n in names]


@pytest.mark.asyncio
async def test_one_invalid_pdf_aborts_whole_batch():
    behaviors = {"a.pdf": "ok", "b.pdf": "invalid_pdf", "c.pdf": "ok"}
    service = BatchAnalysisService(FakeCVService(behaviors))
    with pytest.raises(PDFValidationError) as exc_info:
        await service.analyze_batch(_files(list(behaviors)), CRITERIA)
    assert "b.pdf" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_more_than_five_cvs_is_rejected_before_processing():
    names = [f"{index}.pdf" for index in range(MAX_CV_COUNT + 1)]
    service = BatchAnalysisService(FakeCVService({name: "ok" for name in names}))

    with pytest.raises(PDFValidationError, match="En fazla 5 CV"):
        await service.analyze_batch(_files(names), CRITERIA)


@pytest.mark.asyncio
async def test_llm_failure_aborts_batch_instead_of_returning_incomplete_ranking():
    behaviors = {"a.pdf": "ok", "b.pdf": "llm_fail", "c.pdf": "ok"}
    service = BatchAnalysisService(FakeCVService(behaviors))
    with pytest.raises(LLMOutputValidationError):
        await service.analyze_batch(_files(list(behaviors)), CRITERIA)


@pytest.mark.asyncio
async def test_all_valid_produces_success_status():
    behaviors = {"a.pdf": "ok", "b.pdf": "ok"}
    service = BatchAnalysisService(FakeCVService(behaviors))
    result = await service.analyze_batch(_files(list(behaviors)), CRITERIA)

    assert result.status == "success"
    assert result.processedCVCount == 2


@pytest.mark.asyncio
async def test_five_cvs_produce_only_top_three_candidates():
    names = [f"{index}.pdf" for index in range(MAX_CV_COUNT)]
    service = BatchAnalysisService(FakeCVService({name: "ok" for name in names}))

    result = await service.analyze_batch(_files(names), CRITERIA)

    assert result.processedCVCount == 5
    assert len(result.topCandidates) == 3
    assert [candidate.rank for candidate in result.topCandidates] == [1, 2, 3]
