import pytest

from app.application.cv_analysis_service import CVAnalysisService
from app.domain.errors import LLMOutputValidationError
from app.domain.models import (
    BatchEvaluationItem,
    BatchEvaluationResult,
    BatchCandidateEvaluation,
    BatchProfileItem,
    BatchProfileResult,
    CandidateProfile,
    Criterion,
    CriterionScore,
    EvaluationResult,
)


class FakeLLM:
    def __init__(self, criterion_id: str):
        self.criterion_id = criterion_id
        self.prompts: list[str] = []

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        self.prompts.append(user)
        if response_model is CandidateProfile:
            return CandidateProfile(
                candidateName="Ada",
                contact={},
                summary=None,
                skills=[],
                workExperiences=[],
                education=[],
                languages=[],
            )
        return EvaluationResult(
            scores=[
                CriterionScore(
                    criterionId=self.criterion_id,
                    criterionLabel="modelin değiştirdiği etiket",
                    score=80,
                    evidence=["kanıt"],
                    reason="kanıt",
                )
            ],
            strengths=[],
            weaknesses=[],
            recommendations=[],
            hrEvaluation="uygun",
        )


CRITERIA = [Criterion(id="react", label="React tecrübesi", description="React deneyimi")]


def _profile(name="Ada"):
    return CandidateProfile(
        candidateName=name,
        contact={},
        summary=None,
        skills=["React"],
        workExperiences=[],
        education=[],
        languages=[],
    )


def _evaluation(criterion_id="react"):
    return EvaluationResult(
        scores=[
            CriterionScore(
                criterionId=criterion_id,
                criterionLabel="model etiketi",
                score=80,
                evidence=["React"],
                reason="kanıt",
            )
        ],
        strengths=[],
        weaknesses=[],
        recommendations=[],
        hrEvaluation="uygun",
    )


def _batch_evaluation():
    return BatchCandidateEvaluation(
        scores=_evaluation().scores,
        hrEvaluation="uygun",
    )


class FakeBatchLLM:
    def __init__(self):
        self.prompts = []

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        self.prompts.append(user)
        if response_model is BatchProfileResult:
            return BatchProfileResult(
                candidates=[
                    BatchProfileItem(documentId=0, profile=_profile("Ada")),
                    BatchProfileItem(documentId=1, profile=_profile("Can")),
                ]
            )
        return BatchEvaluationResult(
            candidates=[
                BatchEvaluationItem(documentId=0, evaluation=_batch_evaluation()),
                BatchEvaluationItem(documentId=1, evaluation=_batch_evaluation()),
            ]
        )


@pytest.mark.asyncio
async def test_evaluation_uses_and_enforces_criterion_identity():
    llm = FakeLLM("react")
    _, evaluation = await CVAnalysisService(llm).analyze_from_text("CV metni", CRITERIA)

    assert "id=react" in llm.prompts[1]
    assert evaluation.scores[0].criterionLabel == "React tecrübesi"


@pytest.mark.asyncio
async def test_evaluation_rejects_missing_or_invented_criterion():
    with pytest.raises(LLMOutputValidationError):
        await CVAnalysisService(FakeLLM("invented")).analyze_from_text("CV metni", CRITERIA)


@pytest.mark.asyncio
async def test_batch_uses_two_llm_calls_and_scores_only_normalized_profiles():
    llm = FakeBatchLLM()

    analyses = await CVAnalysisService(llm).analyze_batch_from_texts(
        ["RAW_SECRET_ONE", "RAW_SECRET_TWO"], CRITERIA
    )

    assert len(analyses) == 2
    assert len(llm.prompts) == 2
    assert "RAW_SECRET_ONE" in llm.prompts[0]
    assert "RAW_SECRET_ONE" not in llm.prompts[1]
    assert analyses[0][1].scores[0].criterionLabel == "React tecrübesi"
