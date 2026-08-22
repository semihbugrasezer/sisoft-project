import json

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

    async def extract_text(self, pdf_bytes: bytes) -> tuple[str, bool]:
        filename = pdf_bytes.decode()
        if self.behaviors[filename] == "invalid_pdf":
            raise PDFValidationError(f"{filename} bozuk.")
        return f"text-of-{filename}", self.behaviors[filename] == "truncated"

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
                            evidenceIds=["ev_test"],
                            reason="x",
                        )
                    ],
                    strengths=["x"],
                    weaknesses=["zayıf yön"],
                    recommendations=["tavsiye"],
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
    result, truncated_files = await service.analyze_batch(_files(list(behaviors)), CRITERIA)

    assert result.status == "success"
    assert result.processedCVCount == 2
    assert truncated_files == []


@pytest.mark.asyncio
async def test_five_cvs_produce_only_top_three_candidates():
    names = [f"{index}.pdf" for index in range(MAX_CV_COUNT)]
    service = BatchAnalysisService(FakeCVService({name: "ok" for name in names}))

    result, _ = await service.analyze_batch(_files(names), CRITERIA)

    assert result.processedCVCount == 5
    assert len(result.topCandidates) == 3


@pytest.mark.asyncio
async def test_final_assignment_contract_does_not_leak_internal_evidence():
    names = [f"{index}.pdf" for index in range(MAX_CV_COUNT)]
    service = BatchAnalysisService(FakeCVService({name: "ok" for name in names}))

    result, _ = await service.analyze_batch(_files(names), CRITERIA)
    payload = result.model_dump()
    serialized = json.dumps(payload)

    assert set(payload) == {
        "status", "processedCVCount", "userDefinedCriteria", "topCandidates",
    }
    assert "evidenceId" not in serialized
    assert '"start"' not in serialized
    assert '"end"' not in serialized
    assert [candidate.rank for candidate in result.topCandidates] == [1, 2, 3]


@pytest.mark.asyncio
async def test_truncated_files_are_reported_separately_from_json_contract():
    # Ödevin JSON şeması (MultiAnalysisResponse) `extra="forbid"` ile kilitli —
    # kırpma bilgisini oraya eklemek yerine ayrı döneriz, handlers.py bunu
    # kullanıcıya JSON'dan önce ayrı bir mesajla bildirir.
    behaviors = {"a.pdf": "ok", "b.pdf": "truncated"}
    service = BatchAnalysisService(FakeCVService(behaviors))

    result, truncated_files = await service.analyze_batch(_files(list(behaviors)), CRITERIA)

    assert truncated_files == ["b.pdf"]
    assert "truncated" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_batch_level_truncation_is_reported_to_user():
    # Regresyon: hiçbir dosya tek başına MAX_EXTRACTED_CHARS'ı (20k) aşmasa bile
    # toplam batch bütçesi (60k) aşılırsa metin kırpılır. truncated_files bu
    # durumu da kapsamalı — aksi halde kullanıcı sessiz veri kaybı yaşar.
    names = [f"{i}.pdf" for i in range(5)]
    behaviors = dict.fromkeys(names, "ok")

    class BigCVService(FakeCVService):
        async def extract_text(self, pdf_bytes):
            # 5 × 15k = 75k > 60k bütçe; ama her biri 20k limitinin altında,
            # yani dosya-başı truncated bayrağı False.
            return "x" * 15_000, False

        async def analyze_batch_from_texts(self, texts, criteria):
            # Bu testte önemli olan kırpma bildirimi; profil içeriği değil.
            profile = CandidateProfile(
                candidateName="Aday", contact={}, summary=None, skills=[],
                workExperiences=[], education=[], languages=[],
            )
            evaluation = EvaluationResult(
                scores=[CriterionScore(criterionId="react", criterionLabel="React",
                                       score=80, evidenceIds=["ev_test"], reason="x")],
                strengths=["x"], weaknesses=["zayıf yön"], recommendations=["tavsiye"], hrEvaluation="iyi",
            )
            return [(profile, evaluation) for _ in texts]

    service = BatchAnalysisService(BigCVService(behaviors))
    _, truncated_files = await service.analyze_batch(_files(names), CRITERIA)

    assert truncated_files, "batch bütçesi kırpması kullanıcıya bildirilmedi"
