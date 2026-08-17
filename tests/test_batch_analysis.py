"""BatchAnalysisService'in fail-fast validation ve partial-LLM-failure izolasyonu.
Gerçek Ollama/PDF yok — CVAnalysisService arayüzü (extract_text/analyze_from_text)
sahte (fake) bir implementasyonla değiştirilir."""
import pytest

from app.application.batch_analysis_service import BatchAnalysisService
from app.domain.errors import LLMOutputValidationError, PDFValidationError
from app.domain.models import CandidateProfile, Criterion, CriterionScore, EvaluationResult

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

    async def analyze_from_text(self, text: str, criteria):
        filename = text.replace("text-of-", "")
        if self.behaviors[filename] == "llm_fail":
            raise LLMOutputValidationError("şema hatası")
        profile = CandidateProfile(candidateName=filename)
        evaluation = EvaluationResult(
            scores=[CriterionScore(criterionId="react", criterionLabel="React", score=80, reason="x")],
            strengths=["x"], weaknesses=[], recommendations=[], hrEvaluation="iyi",
        )
        return profile, evaluation


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
async def test_llm_failure_is_isolated_not_batch_wide():
    behaviors = {"a.pdf": "ok", "b.pdf": "llm_fail", "c.pdf": "ok"}
    service = BatchAnalysisService(FakeCVService(behaviors))
    result = await service.analyze_batch(_files(list(behaviors)), CRITERIA)

    assert result.response.processedCVCount == 2
    assert [name for name, _ in result.failed] == ["b.pdf"]
    assert {c.pdfFileName for c in result.response.topCandidates} == {"a.pdf", "c.pdf"}


@pytest.mark.asyncio
async def test_all_valid_produces_success_status():
    behaviors = {"a.pdf": "ok", "b.pdf": "ok"}
    service = BatchAnalysisService(FakeCVService(behaviors))
    result = await service.analyze_batch(_files(list(behaviors)), CRITERIA)

    assert result.response.status == "success"
    assert result.response.processedCVCount == 2
    assert not result.failed
