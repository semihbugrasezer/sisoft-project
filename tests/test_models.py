import pytest
from pydantic import ValidationError

from app.domain.models import (
    CriterionScore,
    EvaluationResult,
    MultiAnalysisResponse,
    TopCandidate,
)


def test_high_score_without_real_evidence_is_rejected():
    with pytest.raises(ValidationError, match="kanıtsız yüksek puan"):
        CriterionScore(
            criterionId="react",
            criterionLabel="React tecrübesi",
            score=95,
            evidence=["Kanıt yok"],
            reason="x",
        )


def test_low_score_without_evidence_is_allowed():
    score = CriterionScore(
        criterionId="react",
        criterionLabel="React tecrübesi",
        score=10,
        evidence=["Kanıt yok"],
        reason="Profilde React'e dair bilgi yok",
    )
    assert score.score == 10


def test_high_score_with_real_evidence_is_allowed():
    score = CriterionScore(
        criterionId="react",
        criterionLabel="React tecrübesi",
        score=90,
        evidence=["5 yıl React ile üretim projesi geliştirdi"],
        reason="Güçlü ve tekrarlanan kanıt",
    )
    assert score.score == 90


def test_criterion_score_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CriterionScore(
            criterionId="react",
            criterionLabel="React tecrübesi",
            score=50,
            evidence=["orta düzey deneyim"],
            reason="x",
            confidence=0.8,  # şemada olmayan alan
        )


def _candidate(rank: int, name: str = "Ada", score: float = 90.0):
    return TopCandidate(
        rank=rank,
        candidateName=name,
        pdfFileName=f"{name.lower()}.pdf",
        dynamicScores={"React": 90},
        averageScore=score,
        hrEvaluation="uygun",
    )


def test_response_rejects_out_of_order_ranks():
    # `extra="forbid"` fazladan alanı engeller ama anlamsız bir sıralamayı
    # engellemez — ödev çıktısı 1..N sıralı rank bekler.
    with pytest.raises(ValidationError, match="rank"):
        MultiAnalysisResponse(
            status="success",
            processedCVCount=2,
            userDefinedCriteria=["React"],
            topCandidates=[_candidate(2, "Ada"), _candidate(1, "Bora")],
        )


def test_response_rejects_more_than_three_candidates():
    with pytest.raises(ValidationError):
        MultiAnalysisResponse(
            status="success",
            processedCVCount=5,
            userDefinedCriteria=["React"],
            topCandidates=[_candidate(i, f"A{i}") for i in range(1, 5)],
        )


def test_response_rejects_unknown_status():
    with pytest.raises(ValidationError):
        MultiAnalysisResponse(
            status="banana",
            processedCVCount=1,
            userDefinedCriteria=["React"],
            topCandidates=[_candidate(1)],
        )


def test_candidate_rejects_score_outside_range():
    with pytest.raises(ValidationError, match="0-100"):
        TopCandidate(
            rank=1,
            candidateName="Ada",
            pdfFileName="ada.pdf",
            dynamicScores={"React": 150},  # aralık dışı
            averageScore=90.0,
            hrEvaluation="uygun",
        )


def _evaluation_kwargs(**overrides):
    base = dict(
        scores=[
            CriterionScore(
                criterionId="react", criterionLabel="React", score=80,
                evidence=["5 yıl React"], reason="x",
            )
        ],
        strengths=["güçlü yön"],
        weaknesses=["zayıf yön"],
        recommendations=["tavsiye"],
        hrEvaluation="uygun",
    )
    base.update(overrides)
    return base


@pytest.mark.parametrize("empty_field", ["strengths", "weaknesses", "recommendations"])
def test_qualitative_report_sections_cannot_be_empty(empty_field):
    # Ödev PDF §2 raporda güçlü yönler, zayıf yönler VE gelişim tavsiyeleri
    # istiyor. Boş liste şemaya uysaydı rapor "(belirtilmedi)" ile çıkardı —
    # kabul testi bunu gerçek bir modelde yakalamıştı. Prompt, gerçek bir zayıf
    # yön yoksa uydurmak yerine "tespit edilmedi" yazmasını söyler.
    with pytest.raises(ValidationError):
        EvaluationResult(**_evaluation_kwargs(**{empty_field: []}))


def test_qualitative_report_accepts_explicit_not_detected_wording():
    # Bölümü doldurmak için sahte bir zayıf yön uydurmak İSTEMİYORUZ; dürüst
    # "tespit edilmedi" ifadesi geçerli bir içeriktir.
    evaluation = EvaluationResult(
        **_evaluation_kwargs(
            weaknesses=["Tanımlanan kriterler kapsamında belirgin bir zayıf yön tespit edilmedi."]
        )
    )
    assert evaluation.weaknesses
