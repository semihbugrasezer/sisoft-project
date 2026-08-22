"""Domain şemaları. LLM çıktıları Pydantic modellerine zorlanır (docs/LLM_PIPELINE.md)."""
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

    @field_validator("label")
    @classmethod
    def humanize_label(cls, value: str) -> str:
        return " ".join(value.replace("_", " ").split())


class CriteriaExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_criteria(self):
        ids = [criterion.id for criterion in self.criteria]
        labels = [criterion.label.casefold() for criterion in self.criteria]
        if len(set(ids)) != len(ids) or len(set(labels)) != len(labels):
            raise ValueError("Kriter kimlikleri ve etiketleri benzersiz olmalıdır.")
        return self


class CriteriaIntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class EvidenceQuoteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=3, max_length=320)


class CriterionEvidenceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterionId: str
    items: list[EvidenceQuoteDraft] = Field(default_factory=list, max_length=3)

    @field_validator("criterionId")
    @classmethod
    def strip_criterion_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("criterionId boş olamaz.")
        return value


class CandidateProfile(BaseModel):
    """PDF'in ortak profil şemasıyla birebir. `extra="forbid"`: LLM extraction'ın
    şema dışına taşmadığını (uydurma alan üretmediğini) garanti eder
    (docs/LLM_PIPELINE.md)."""

    model_config = ConfigDict(extra="forbid")

    candidateName: str | None
    contact: Contact
    summary: str | None
    skills: list[str]
    workExperiences: list[WorkExperience]
    education: list[Education]
    languages: list[Language]


class NormalizedCandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: CandidateProfile
    criterionEvidence: list[CriterionEvidenceDraft] = Field(min_length=1)


class EvidenceExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterionEvidence: list[CriterionEvidenceDraft] = Field(min_length=1)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidenceId: str
    quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def end_follows_start(self):
        if self.end <= self.start:
            raise ValueError("Evidence end değeri start değerinden büyük olmalıdır.")
        return self


class GroundedCriterionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterionId: str
    items: list[EvidenceRecord] = Field(default_factory=list, max_length=3)


class GroundedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: CandidateProfile
    criterionEvidence: list[GroundedCriterionEvidence] = Field(min_length=1)


class VerifiedEvidence(EvidenceRecord):
    relation: Literal["supports", "contradicts"]


class CriterionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterionId: str
    items: list[VerifiedEvidence] = Field(default_factory=list, max_length=3)


class NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: CandidateProfile
    criterionEvidence: list[CriterionEvidence] = Field(min_length=1)


class BatchProfileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documentId: int
    candidate: NormalizedCandidateDraft


class BatchProfileResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[BatchProfileItem] = Field(min_length=1, max_length=MAX_CV_COUNT)


# --- Değerlendirme (CandidateEvaluator çıktısı) -------------------------

class EvidenceVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidenceId: str
    verdict: Literal["supports", "contradicts", "irrelevant"]


class EvidenceVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[EvidenceVerdict]


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterionId: str
    criterionLabel: str
    score: int = Field(ge=0, le=100)
    evidenceIds: list[str] = Field(default_factory=list)
    reason: str


class EvaluationResult(BaseModel):
    """Tekli CV raporu. Ödev PDF §2 raporda güçlü yönler, zayıf yönler VE gelişim
    tavsiyelerinin kullanıcıya sunulmasını istiyor — üçü de opsiyonel değildir.

    `min_length=1`: boş liste şemaya uysaydı rapor "Zayıf Yönler: (belirtilmedi)"
    ile çıkardı; kabul testi bunu gerçek bir modelde yakaladı. Prompt, gerçek bir
    zayıf yön yoksa UYDURMAK yerine "tespit edilmedi" yazmasını söyler — bölüm
    dolu kalır ama içerik dürüst olur. Boş liste gelirse ValidationError,
    structured_chat'in mevcut tek-seferlik düzeltme retry'ını tetikler."""

    model_config = ConfigDict(extra="forbid")

    scores: list[CriterionScore]
    strengths: list[str] = Field(min_length=1)
    weaknesses: list[str] = Field(min_length=1)
    recommendations: list[str] = Field(min_length=1)
    hrEvaluation: str = Field(description="tek cümlelik özet değerlendirme")


class BatchCandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[CriterionScore]
    hrEvaluation: str = Field(description="tek cümlelik özet değerlendirme")


class BatchEvaluationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documentId: int
    evaluation: BatchCandidateEvaluation


class BatchEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[BatchEvaluationItem] = Field(min_length=1, max_length=MAX_CV_COUNT)


# --- Çoklu CV nihai çıktı — ödev PDF §4 şemasıyla birebir ----------------

class TopCandidate(BaseModel):
    """Alan adları ödev PDF §4 ile birebir. Aralıklar da sözleşmenin parçası:
    `extra="forbid"` yalnızca *fazladan alan* eklenmesini engeller, anlamsız bir
    değeri (rank=0, score=999) engellemez — bu yüzden sınırlar açıkça verilir."""

    model_config = ConfigDict(extra="forbid")

    # rank alan seviyesinde sınırlanmaz: `rank_top_n` çağrılmadan önce aday
    # nesneleri rank=0 ile kurulur (sıralama henüz bilinmiyor). Asıl sözleşme
    # MultiAnalysisResponse.ranks_are_sequential'da doğrulanır — orası kullanıcıya
    # giden çıktıdır ve 1..N sıralılığını kontrol etmek `ge=1` demekten daha güçlüdür.
    rank: int = Field(ge=0)
    candidateName: str
    pdfFileName: str
    dynamicScores: dict[str, int]
    averageScore: float = Field(ge=0, le=100)
    hrEvaluation: str

    @field_validator("dynamicScores")
    @classmethod
    def scores_within_range(cls, value: dict[str, int]) -> dict[str, int]:
        out_of_range = {k: v for k, v in value.items() if not 0 <= v <= 100}
        if out_of_range:
            raise ValueError(f"Skorlar 0-100 aralığında olmalı: {out_of_range}")
        return value


class MultiAnalysisResponse(BaseModel):
    """Ödev PDF §4 şemasıyla birebir — extra alan eklenirse (failedCVs, confidence vb.)
    validation hatası fırlatır, çıktı sözleşmesi kazayla bozulamaz."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"]
    processedCVCount: int = Field(ge=1, le=MAX_CV_COUNT)
    userDefinedCriteria: list[str] = Field(min_length=1)
    topCandidates: list[TopCandidate] = Field(max_length=3)

    @model_validator(mode="after")
    def ranks_are_sequential(self):
        expected = list(range(1, len(self.topCandidates) + 1))
        actual = [candidate.rank for candidate in self.topCandidates]
        if actual != expected:
            raise ValueError(f"rank değerleri 1..N sırasıyla olmalı, alınan: {actual}")
        return self

    @model_validator(mode="after")
    def candidate_count_matches_processed(self):
        """Aday sayısı işlenen CV sayısıyla tutarlı olmalı: 3+ CV işlendiyse tam 3
        aday, daha azsa işlenen kadar. Yalnız `max_length=3` demek yetmez — 5 CV
        işlenip 2 aday dönmesi şemadan geçerdi ama ödevin top-3 sözleşmesini
        sessizce bozardı."""
        expected = min(3, self.processedCVCount)
        if len(self.topCandidates) != expected:
            raise ValueError(
                f"processedCVCount={self.processedCVCount} için {expected} aday "
                f"beklenirdi, {len(self.topCandidates)} geldi"
            )
        return self
