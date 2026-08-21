import pytest

from app.application.cv_analysis_service import MAX_BATCH_EXTRACTED_CHARS, CVAnalysisService
from app.domain.errors import LLMOutputValidationError
from app.domain.models import (
    BatchCandidateEvaluation,
    BatchEvaluationItem,
    BatchEvaluationResult,
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
                skills=["React"],
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
                    evidence=["React"],
                    reason="kanıt",
                )
            ],
            strengths=["güçlü yön"],
            weaknesses=["zayıf yön"],
            recommendations=["tavsiye"],
            hrEvaluation="uygun",
        )


CRITERIA = [
    Criterion(
        id="react",
        label="React tecrübesi",
        description="React deneyimi",
        evidenceHints=["React.js üretim projesi"],
    )
]


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
        strengths=["güçlü yön"],
        weaknesses=["zayıf yön"],
        recommendations=["tavsiye"],
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
    _, evaluation = await CVAnalysisService(llm).analyze_from_text(
        "Ada Lovelace — React CV metni", CRITERIA
    )

    assert "id=react" in llm.prompts[1]
    assert "React.js üretim projesi" in llm.prompts[1]
    assert evaluation.scores[0].criterionLabel == "React tecrübesi"


@pytest.mark.asyncio
async def test_evaluation_rejects_missing_or_invented_criterion():
    with pytest.raises(LLMOutputValidationError):
        await CVAnalysisService(FakeLLM("invented")).analyze_from_text(
            "Ada Lovelace — CV metni", CRITERIA
        )


@pytest.mark.asyncio
async def test_high_score_evidence_must_exist_in_normalized_profile():
    class UngroundedEvidenceLLM:
        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            if response_model is CandidateProfile:
                return _profile()
            return EvaluationResult(
                scores=[
                    CriterionScore(
                        criterionId="react",
                        criterionLabel="React tecrübesi",
                        score=95,
                        evidence=["Kubernetes ile 10 yıl deneyim"],
                        reason="uydurulmuş kanıt",
                    )
                ],
                strengths=["x"],
                weaknesses=["x"],
                recommendations=["x"],
                hrEvaluation="x",
            )

    _, evaluation = await CVAnalysisService(UngroundedEvidenceLLM()).analyze_from_text(
        "Ada\nReact",
        CRITERIA,
    )

    assert evaluation.scores[0].score == 0
    assert evaluation.scores[0].evidence == ["Kanıt yok"]


@pytest.mark.asyncio
async def test_high_score_evidence_may_explain_a_fact_that_exists_in_profile():
    class GroundedParaphraseLLM:
        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            if response_model is CandidateProfile:
                return _profile()
            return EvaluationResult(
                scores=[
                    CriterionScore(
                        criterionId="react",
                        criterionLabel="React tecrübesi",
                        score=80,
                        evidence=["Aday React alanında deneyimlidir"],
                        reason="React profile içinde yer alıyor",
                    )
                ],
                strengths=["x"],
                weaknesses=["x"],
                recommendations=["x"],
                hrEvaluation="x",
            )

    _, evaluation = await CVAnalysisService(GroundedParaphraseLLM()).analyze_from_text(
        "Ada\nReact",
        CRITERIA,
    )

    assert evaluation.scores[0].score == 80


class EvidenceLLM:
    def __init__(self, profile: CandidateProfile, evaluation: EvaluationResult):
        self.profile = profile
        self.evaluation = evaluation

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        return self.profile if response_model is CandidateProfile else self.evaluation


def _scored_evaluation(
    criterion: Criterion, evidence: str, score: int = 95
) -> EvaluationResult:
    return EvaluationResult(
        scores=[
            CriterionScore(
                criterionId=criterion.id,
                criterionLabel=criterion.label,
                score=score,
                evidence=[evidence],
                reason="x",
            )
        ],
        strengths=["x"],
        weaknesses=["x"],
        recommendations=["x"],
        hrEvaluation="x",
    )


@pytest.mark.asyncio
async def test_high_score_rejects_evidence_with_one_real_and_one_invented_claim():
    llm = EvidenceLLM(_profile(), _scored_evaluation(CRITERIA[0], "React ve Kubernetes"))

    _, evaluation = await CVAnalysisService(llm).analyze_from_text("Ada\nReact", CRITERIA)

    assert evaluation.scores[0].score == 0


@pytest.mark.asyncio
async def test_high_score_rejects_invented_numeric_claim():
    llm = EvidenceLLM(_profile(), _scored_evaluation(CRITERIA[0], "React ile 10 yıl"))

    _, evaluation = await CVAnalysisService(llm).analyze_from_text("Ada\nReact", CRITERIA)

    assert evaluation.scores[0].score == 0


@pytest.mark.asyncio
async def test_cross_language_criterion_accepts_fully_source_grounded_evidence():
    criterion = Criterion(id="clean_code", label="Temiz kod yazımı", description="temiz kod")
    profile = _profile().model_copy(update={"skills": ["Clean Code"]})
    llm = EvidenceLLM(profile, _scored_evaluation(criterion, "Clean Code"))

    _, evaluation = await CVAnalysisService(llm).analyze_from_text(
        "Ada\nClean Code", [criterion]
    )

    assert evaluation.scores[0].score == 95


@pytest.mark.asyncio
async def test_high_score_evidence_must_exist_in_raw_source_not_only_profile():
    criterion = Criterion(id="k8s", label="Kubernetes", description="Kubernetes")
    profile = _profile().model_copy(update={"skills": ["Kubernetes"]})
    llm = EvidenceLLM(profile, _scored_evaluation(criterion, "Kubernetes"))

    _, evaluation = await CVAnalysisService(llm).analyze_from_text("Ada\nReact", [criterion])

    assert evaluation.scores[0].score == 0


@pytest.mark.asyncio
async def test_batch_downgrades_cross_candidate_evidence_instead_of_aborting():
    class LeakyBatchLLM(FakeBatchLLM):
        async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
            if response_model is BatchProfileResult:
                return await super().structured_chat(
                    system, user, response_model, temperature, model
                )
            leaked = _scored_evaluation(CRITERIA[0], "React ve Kubernetes").scores
            return BatchEvaluationResult(
                candidates=[
                    BatchEvaluationItem(
                        documentId=index,
                        evaluation=BatchCandidateEvaluation(
                            scores=leaked,
                            hrEvaluation="uygun",
                        ),
                    )
                    for index in range(2)
                ]
            )

    analyses = await CVAnalysisService(LeakyBatchLLM()).analyze_batch_from_texts(
        ["Ada React", "Can React"], CRITERIA
    )

    assert [item[1].scores[0].score for item in analyses] == [0, 0]


@pytest.mark.asyncio
async def test_ungrounded_extracted_skill_is_removed_from_normalized_profile():
    criterion = Criterion(id="k8s", label="Kubernetes", description="Kubernetes")
    profile = _profile().model_copy(update={"skills": ["Kubernetes"]})
    llm = EvidenceLLM(
        profile,
        _scored_evaluation(criterion, "Kanıt yok", score=0),
    )

    normalized, _ = await CVAnalysisService(llm).analyze_from_text(
        "Ada\nReact", [criterion]
    )

    assert normalized.skills == []


@pytest.mark.asyncio
async def test_batch_uses_two_llm_calls_and_scores_only_normalized_profiles():
    llm = FakeBatchLLM()

    analyses = await CVAnalysisService(llm).analyze_batch_from_texts(
        ["Ada React RAW_SECRET_ONE", "Can React RAW_SECRET_TWO"], CRITERIA
    )

    assert len(analyses) == 2
    assert len(llm.prompts) == 2
    assert "RAW_SECRET_ONE" in llm.prompts[0]
    assert "RAW_SECRET_ONE" not in llm.prompts[1]
    assert analyses[0][1].scores[0].criterionLabel == "React tecrübesi"


def test_batch_budget_leaves_small_documents_untouched():
    texts = ["a" * 100, "b" * 200]
    fitted, trimmed = CVAnalysisService.fit_batch_budget(texts)
    assert fitted == texts
    assert trimmed == []


def test_batch_budget_trims_only_when_total_exceeds_limit():
    # 5 belge × 20.000 = 100.000 karakter tek prompt'a girerse yerel modelin
    # context window'unu taşırabilir; toplam bütçe uygulanmalı.
    texts = ["x" * 20_000] * 5
    fitted, _ = CVAnalysisService.fit_batch_budget(texts)

    assert sum(len(t) for t in fitted) <= MAX_BATCH_EXTRACTED_CHARS
    assert all(len(t) > 0 for t in fitted)  # hiçbir belge tamamen silinmez


def test_batch_budget_redistributes_unused_share_to_long_documents():
    # Kısa belgeler payını kullanmazsa artan bütçe uzun belgeye verilmeli —
    # aksi halde uzun CV gereksiz yere kırpılırdı.
    texts = ["s" * 10, "L" * 100_000]
    fitted, _ = CVAnalysisService.fit_batch_budget(texts)

    assert fitted[0] == texts[0]  # kısa belge dokunulmadan kalır
    half = MAX_BATCH_EXTRACTED_CHARS // 2
    assert len(fitted[1]) > half  # artan pay uzun belgeye aktarıldı


class FakeCorruptingLLM:
    """İlk extraction'da adı bozar (canlı koşuda gözlenen davranış), düzeltme
    turunda doğru adı verir."""

    def __init__(self, fix_on_retry: bool = True):
        self.fix_on_retry = fix_on_retry
        self.extraction_calls = 0

    async def structured_chat(self, system, user, response_model, temperature=0.0, model=None):
        if response_model is CandidateProfile:
            self.extraction_calls += 1
            correct = self.extraction_calls > 1 and self.fix_on_retry
            return CandidateProfile(
                candidateName="Semih Buğra Sezer" if correct else "Semhi Bügüra Sezer",
                contact={}, summary=None, skills=["React"], workExperiences=[],
                education=[], languages=[],
            )
        return _evaluation()


SOURCE_WITH_NAME = "Semih Buğra Sezer\nYazılım Geliştirici\nReact"


@pytest.mark.asyncio
async def test_corrupted_candidate_name_triggers_retry_and_is_fixed():
    llm = FakeCorruptingLLM(fix_on_retry=True)
    profile, _ = await CVAnalysisService(llm).analyze_from_text(SOURCE_WITH_NAME, CRITERIA)

    assert llm.extraction_calls == 2, "grounding düzeltme turunu tetiklemeliydi"
    assert profile.candidateName == "Semih Buğra Sezer"


@pytest.mark.asyncio
async def test_still_ungrounded_name_falls_back_to_none():
    # Düzeltme turu da bozuk ad dönerse uydurma veriyi rapora taşımak yerine
    # None'a çekilir; çağıranlar dosya adına düşer.
    llm = FakeCorruptingLLM(fix_on_retry=False)
    profile, _ = await CVAnalysisService(llm).analyze_from_text(SOURCE_WITH_NAME, CRITERIA)

    assert llm.extraction_calls == 2
    assert profile.candidateName is None
