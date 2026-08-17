import pytest

from app.application.criteria_service import CriteriaService
from app.domain.models import CriteriaExtractionResult, Criterion


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def structured_chat(self, system, user, response_model):
        self.calls += 1
        label = "Proje yönetimi" if self.calls == 1 else "React tecrübesi"
        return CriteriaExtractionResult(
            criteria=[Criterion(id="react", label=label, description="React deneyimi")]
        )


class FakeRepo:
    def __init__(self):
        self.saved = None

    async def set_criteria(self, chat_id, criteria):
        self.saved = criteria


@pytest.mark.asyncio
async def test_retries_and_drops_criterion_not_present_in_user_text():
    llm = FakeLLM()
    repo = FakeRepo()
    criteria = await CriteriaService(llm, repo).define_criteria(
        1, "React tecrübesine göre değerlendir"
    )

    assert llm.calls == 2
    assert [criterion.label for criterion in criteria] == ["React tecrübesi"]
    assert repo.saved[0]["label"] == "React tecrübesi"


def test_keeps_semantic_label_but_drops_unrelated_extra_criterion():
    criteria = [
        Criterion(id="react", label="React deneyimi", description="x"),
        Criterion(id="pm", label="Proje yönetimi", description="x"),
    ]
    grounded = CriteriaService._grounded_criteria(
        criteria, "React tecrübesine göre değerlendir"
    )
    assert [criterion.id for criterion in grounded] == ["react"]


def test_keeps_short_or_symbolic_exact_criterion():
    criteria = [Criterion(id="cpp", label="C++", description="x")]
    assert CriteriaService._grounded_criteria(criteria, "C++ bilgisine göre değerlendir")
