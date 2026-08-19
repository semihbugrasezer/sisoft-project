import pytest
from pydantic import ValidationError

from app.domain.models import CriterionScore


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
