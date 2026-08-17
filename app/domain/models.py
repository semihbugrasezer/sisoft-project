"""Domain şemaları. LLM çıktıları Pydantic modellerine zorlanır (RULES.md §3-5)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CV_COUNT = 5


# --- Kriter (CriteriaExtractor çıktısı) ---------------------------------

class Criterion(BaseModel):
    id: str = Field(description="snake_case kısa kimlik, örn. react_experience")
    label: str = Field(description="kullanıcının kullandığı orijinal kriter adı")
    description: str
    evidenceHints: list[str] = Field(default_factory=list)

    @field_validator("id", "label")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Kriter kimliği ve etiketi boş olamaz.")
        return value


class CriteriaExtractionResult(BaseModel):
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_criteria(self):
        ids = [criterion.id for criterion in self.criteria]
        labels = [criterion.label.casefold() for criterion in self.criteria]
        if len(set(ids)) != len(ids) or len(set(labels)) != len(labels):
            raise ValueError("Kriter kimlikleri ve etiketleri benzersiz olmalıdır.")
        return self


class CriteriaIntentResult(BaseModel):
    intent: Literal["criteria", "chat"]
    criteria: list[Criterion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_intent_payload(self):
        if self.intent == "criteria":
            CriteriaExtractionResult(criteria=self.criteria)
        elif self.criteria:
            raise ValueError("Sohbet mesajı kriter içeremez.")
        return self


# --- CV profili (CVExtractor çıktısı) -----------------------------------

class Contact(BaseModel):
    email: str | None = None
    phone: str | None = None
    location: str | None = None


class WorkExperience(BaseModel):
    company: str | None = None
    title: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    description: str | None = None


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    graduationDate: str | None = None


class Language(BaseModel):
    name: str
    level: str | None = None


class CandidateProfile(BaseModel):
    candidateName: str | None
    contact: Contact
    summary: str | None
    skills: list[str]
    workExperiences: list[WorkExperience]
    education: list[Education]
    languages: list[Language]


class BatchProfileItem(BaseModel):
    documentId: int
    profile: CandidateProfile


class BatchProfileResult(BaseModel):
    candidates: list[BatchProfileItem] = Field(min_length=1, max_length=MAX_CV_COUNT)


# --- Değerlendirme (CandidateEvaluator çıktısı) -------------------------

class CriterionScore(BaseModel):
    criterionId: str
    criterionLabel: str
    score: int = Field(ge=0, le=100)
    evidence: list[str] = Field(
        min_length=1,
        description="Profildeki somut kanıtlar; kanıt yoksa tek eleman olarak 'Kanıt yok'",
    )
    reason: str


class EvaluationResult(BaseModel):
    scores: list[CriterionScore]
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]
    hrEvaluation: str = Field(description="tek cümlelik özet değerlendirme")


class BatchCandidateEvaluation(BaseModel):
    scores: list[CriterionScore]
    hrEvaluation: str = Field(description="tek cümlelik özet değerlendirme")


class BatchEvaluationItem(BaseModel):
    documentId: int
    evaluation: BatchCandidateEvaluation


class BatchEvaluationResult(BaseModel):
    candidates: list[BatchEvaluationItem] = Field(min_length=1, max_length=MAX_CV_COUNT)


# --- Çoklu CV nihai çıktı — ödev PDF §4 şemasıyla birebir ----------------

class TopCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    candidateName: str
    pdfFileName: str
    dynamicScores: dict[str, int]
    averageScore: float
    hrEvaluation: str


class MultiAnalysisResponse(BaseModel):
    """Ödev PDF §4 şemasıyla birebir — extra alan eklenirse (failedCVs, confidence vb.)
    validation hatası fırlatır, çıktı sözleşmesi kazayla bozulamaz."""

    model_config = ConfigDict(extra="forbid")

    status: str
    processedCVCount: int
    userDefinedCriteria: list[str]
    topCandidates: list[TopCandidate]
