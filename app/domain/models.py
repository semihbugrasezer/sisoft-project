"""Domain şemaları. LLM çıktıları Pydantic modellerine zorlanır (README.md §3-5)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CV_COUNT = 5


# --- Kriter (CriteriaExtractor çıktısı) ---------------------------------

class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class WorkExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str | None = None
    title: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    description: str | None = None


class Education(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    graduationDate: str | None = None


class Language(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    level: str | None = None


class CandidateProfile(BaseModel):
    """PDF'in ortak profil şemasıyla birebir. `extra="forbid"`: LLM extraction'ın
    şema dışına taşmadığını (uydurma alan üretmediğini) garanti eder — extraction
    kalitesi rubric'te doğrudan ölçülüyor (README.md §8)."""

    model_config = ConfigDict(extra="forbid")

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

# Prompt "kanıt yoksa evidence'a tek eleman olarak 'Kanıt yok' yaz, düşük puan ver"
# diyor (CANDIDATE_EVALUATOR_SYSTEM) ama bu yalnızca prompt seviyesinde bir kural —
# model_config alanları ve Field(min_length=1) tek başına "score=95, evidence=['Kanıt
# yok']" gibi teknik olarak şemaya uyan ama semantik olarak tutarsız bir çıktıyı
# engellemez. Aşağıdaki validator bunu reddeder; ValidationError, OllamaClient.
# structured_chat'in zaten sahip olduğu tek-seferlik şema-düzeltme retry'ını tetikler
# (ayrı bir retry mekanizması eklemeye gerek yok).
_NO_EVIDENCE_MARKERS = {"kanıt yok", "kanit yok", "no evidence", "yok", "-"}


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterionId: str
    criterionLabel: str
    score: int = Field(ge=0, le=100)
    evidence: list[str] = Field(
        min_length=1,
        description="Profildeki somut kanıtlar; kanıt yoksa tek eleman olarak 'Kanıt yok'",
    )
    reason: str

    @model_validator(mode="after")
    def require_real_evidence_for_high_score(self):
        has_real_evidence = any(
            item.strip().casefold() not in _NO_EVIDENCE_MARKERS for item in self.evidence
        )
        if self.score >= 20 and not has_real_evidence:
            raise ValueError(
                f"score={self.score} (>= 20) ama evidence yalnızca 'kanıt yok' türünden "
                "placeholder içeriyor — kanıtsız yüksek puan kabul edilmez."
            )
        return self


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[CriterionScore]
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]
    hrEvaluation: str = Field(description="tek cümlelik özet değerlendirme")


class BatchCandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
