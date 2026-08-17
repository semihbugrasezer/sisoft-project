import pytest

from app.application.cv_analysis_service import CVAnalysisService
from app.domain.errors import LLMOutputValidationError
from app.domain.models import CandidateProfile, Criterion, CriterionScore, EvaluationResult


class FakeLLM:
    def __init__(self, criterion_id: str):
        self.criterion_id = criterion_id
        self.prompts: list[str] = []

    async def structured_chat(self, system, user, response_model):
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
