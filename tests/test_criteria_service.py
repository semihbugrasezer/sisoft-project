import pytest

from app.application.criteria_service import CriteriaService
from pydantic import ValidationError

from app.domain.errors import LLMOutputValidationError
from app.domain.models import CriteriaExtractionResult, CriteriaIntentResult, Criterion
from app.infrastructure.llm.prompts import CRITERIA_EXTRACTOR_SYSTEM


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
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


def test_dynamic_criteria_has_no_arbitrary_eight_item_limit():
    result = CriteriaExtractionResult(
        criteria=[
            Criterion(id=f"criterion_{index}", label=f"Kriter {index}", description="x")
            for index in range(9)
        ]
    )
    assert len(result.criteria) == 9
    assert "1 ile 8" not in CRITERIA_EXTRACTOR_SYSTEM


@pytest.mark.asyncio
async def test_free_text_without_keyword_can_define_criteria():
    class IntentLLM:
        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            assert response_model is CriteriaIntentResult
            return CriteriaIntentResult(
                intent="criteria",
                criteria=[
                    Criterion(
                        id="react",
                        label="React tecrübesi",
                        description="React deneyimi",
                    )
                ],
            )

    repo = FakeRepo()
    criteria = await CriteriaService(IntentLLM(), repo).define_if_requested(
        1, "React tecrübesi benim için önemli"
    )

    assert [criterion.label for criterion in criteria] == ["React tecrübesi"]
    assert repo.saved[0]["id"] == "react"


@pytest.mark.asyncio
async def test_define_if_requested_uses_configured_intent_model():
    class IntentModelSpyLLM:
        def __init__(self):
            self.seen_models: list[str | None] = []

        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            self.seen_models.append(model)
            return CriteriaIntentResult(intent="chat", criteria=[])

    llm = IntentModelSpyLLM()
    service = CriteriaService(llm, FakeRepo(), intent_model="qwen2.5:1.5b")

    result = await service.define_if_requested(1, "bugün nasılsın?")

    assert result is None
    assert llm.seen_models == ["qwen2.5:1.5b"]


@pytest.mark.asyncio
async def test_define_if_requested_defaults_to_main_model_when_unconfigured():
    class IntentModelSpyLLM:
        def __init__(self):
            self.seen_models: list[str | None] = []

        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            self.seen_models.append(model)
            return CriteriaIntentResult(intent="chat", criteria=[])

    llm = IntentModelSpyLLM()
    service = CriteriaService(llm, FakeRepo())  # intent_model verilmedi

    await service.define_if_requested(1, "bugün nasılsın?")

    assert llm.seen_models == [None]  # OllamaClient bunu ana modele düşürür


@pytest.mark.asyncio
async def test_define_if_requested_falls_back_to_chat_when_intent_schema_invalid():
    # Zayıf modellerde (canlı testte 0.5B) intent-classification iki denemede de şemaya
    # uygun JSON üretemeyebilir. Kullanıcıyı hata mesajıyla çıkmaza sokmak yerine
    # mesajı chat olarak ele almalıyız (bkz. README.md → Teknik Altyapı).
    class FailingIntentLLM:
        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            raise LLMOutputValidationError("Model beklenen formatta yanıt üretemedi.")

    result = await CriteriaService(FailingIntentLLM(), FakeRepo()).define_if_requested(
        1, "merhaba nasılsın"
    )

    assert result is None


def test_blank_or_duplicate_criteria_are_rejected():
    with pytest.raises(ValidationError):
        Criterion(id=" ", label="React", description="x")
    with pytest.raises(ValidationError):
        CriteriaExtractionResult(
            criteria=[
                Criterion(id="react", label="React", description="x"),
                Criterion(id="react", label="Clean Code", description="x"),
            ]
        )
