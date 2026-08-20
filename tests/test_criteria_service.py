import pytest
from pydantic import ValidationError

from app.application.criteria_service import CriteriaService
from app.domain.errors import IntentUndecidableError, LLMOutputValidationError
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


class FakeLLMParaphrasedLabel:
    """Model kullanıcının ifadesini hafifçe yeniden yazar: "React tecrübesi" ->
    "React deneyimi". Anlam korunur ve etiket kullanıcının kelimesine dayanır."""

    def __init__(self):
        self.calls = 0

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        self.calls += 1
        return CriteriaExtractionResult(
            criteria=[Criterion(id="react", label="React deneyimi", description="x")]
        )


@pytest.mark.asyncio
async def test_semantically_grounded_paraphrase_is_accepted():
    # Regresyon: bir dönem birebir-etiket zorunluluğu vardı ve parafrazı reddedip
    # fazladan bir düzeltme turu tetikliyordu. Bu kısıt ödev PDF'inden gelmiyor —
    # PDF'in kendi JSON örneği userDefinedCriteria içinde "Clean Code" gösteriyor,
    # oysa düz metin örneğinde kullanıcı "temiz kod yazımı" yazıyor. Gereken
    # kriterin kullanıcının söylediğine DAYANMASI (grounded olması); kelimesi
    # kelimesine aynı olması değil.
    llm = FakeLLMParaphrasedLabel()
    criteria = await CriteriaService(llm, FakeRepo()).define_criteria(
        1, "React tecrübesine göre değerlendir"
    )

    assert llm.calls == 1, "parafraz için gereksiz düzeltme turu tetiklendi"
    assert criteria[0].label == "React deneyimi"


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
async def test_define_if_requested_raises_explicit_error_when_intent_undecidable():
    # Zayıf modellerde (canlı testte 0.5B) intent-classification şemaya uygun JSON
    # üretemeyebilir. Mesajı sessizce "chat" saymak, kullanıcının kriter tanımını
    # kaybetmek olurdu ve kullanıcı bunu ancak CV gönderdiğinde fark ederdi —
    # dinamik kriter yakalama ödevin çekirdek gereksinimi. Açık hata + yönlendirme
    # tercih edilir.
    class FailingIntentLLM:
        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            raise LLMOutputValidationError("Model beklenen formatta yanıt üretemedi.")

    with pytest.raises(IntentUndecidableError) as exc_info:
        await CriteriaService(FailingIntentLLM(), FakeRepo()).define_if_requested(
            1, "React tecrübesi benim için önemli"
        )

    # Kullanıcı ne yapacağını bilmeli
    assert "/criteria" in exc_info.value.user_message


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


class FakeIntentFailsThenMainWorks:
    """Küçük intent modeli şema hatası verir; ana model (model=None) başarır."""

    def __init__(self):
        self.models_tried = []

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        self.models_tried.append(model)
        if model is not None:
            raise LLMOutputValidationError("küçük model şema üretemedi")
        return CriteriaIntentResult(
            intent="criteria",
            criteria=[Criterion(id="react", label="React tecrübesi", description="x")],
        )


@pytest.mark.asyncio
async def test_intent_failure_retries_with_main_model():
    # Sessiz hata regresyonu: küçük intent modeli JSON üretemezse mesaj doğrudan
    # "chat" sayılıyordu ve kullanıcının kriter tanımı sessizce kayboluyordu.
    llm = FakeIntentFailsThenMainWorks()
    criteria = await CriteriaService(llm, FakeRepo(), intent_model="tiny").define_if_requested(
        1, "React tecrübesi benim için önemli"
    )

    assert llm.models_tried == ["tiny", None], "ana modelle tekrar denenmedi"
    assert criteria is not None and criteria[0].label == "React tecrübesi"


class FakeAlwaysFailsIntent:
    def __init__(self):
        self.calls = 0

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        self.calls += 1
        raise LLMOutputValidationError("şema hatası")


@pytest.mark.asyncio
async def test_intent_failure_on_both_models_raises_explicit_error():
    # Küçük model başarısız olunca ana model denenir; o da başarısızsa sessizce
    # sohbete düşmek yerine açık hata dönülür.
    llm = FakeAlwaysFailsIntent()
    with pytest.raises(IntentUndecidableError):
        await CriteriaService(llm, FakeRepo(), intent_model="tiny").define_if_requested(
            1, "merhaba"
        )

    assert llm.calls == 2, "ana model denenmeden hata dönüldü"


class FakeIntentUngroundedThenGrounded:
    """Intent çağrısı kullanıcının hiç bahsetmediği bir kriter uydurur;
    define_criteria düzeltme turu gerçek kriteri verir."""

    def __init__(self):
        self.calls = 0

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        self.calls += 1
        if response_model is CriteriaIntentResult:
            return CriteriaIntentResult(
                intent="criteria",
                criteria=[Criterion(id="pm", label="Proje yönetimi", description="x")],
            )
        return CriteriaExtractionResult(
            criteria=[Criterion(id="react", label="React tecrübesi", description="x")]
        )


@pytest.mark.asyncio
async def test_natural_language_path_shares_grounding_correction():
    # Doğal dil akışı ile /criteria akışı AYNI doğrulamadan geçmeli: intent çağrısı
    # kullanıcı metnine dayanmayan bir kriter üretirse düzeltme turu (define_criteria
    # içinde) devreye girmeli, uydurma kriter kaydedilmemeli.
    llm = FakeIntentUngroundedThenGrounded()
    criteria = await CriteriaService(llm, FakeRepo()).define_if_requested(
        1, "React tecrübesine göre değerlendir"
    )

    assert criteria is not None
    assert criteria[0].label == "React tecrübesi"
