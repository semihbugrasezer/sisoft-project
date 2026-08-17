"""Domain şemaları. LLM çıktıları bu Pydantic modellerine zorlanır (bkz. RULES.md §5-7)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --- Kriter (CriteriaExtractor çıktısı) ---------------------------------

class Criterion(BaseModel):
    id: str = Field(description="snake_case kısa kimlik, örn. react_experience")
    label: str = Field(description="kullanıcının kullandığı orijinal kriter adı")
    description: str
    evidenceHints: list[str] = Field(default_factory=list)


class CriteriaExtractionResult(BaseModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=8)


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
    candidateName: str | None = None
    contact: Contact = Field(default_factory=Contact)
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    workExperiences: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)


# --- Değerlendirme (CandidateEvaluator çıktısı) -------------------------

class CriterionScore(BaseModel):
    criterionId: str
    criterionLabel: str
    score: int = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    reason: str


class EvaluationResult(BaseModel):
    scores: list[CriterionScore]
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]
    hrEvaluation: str = Field(description="tek cümlelik özet değerlendirme")


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
