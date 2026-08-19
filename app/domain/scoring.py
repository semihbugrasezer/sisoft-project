"""Ortalama ve sıralama — LLM'den bağımsız saf fonksiyonlar (README.md → Çoklu CV Skorlama ve Sıralama).
Ortalama backend'de hesaplanır: kanıtlanabilir ve deterministik olsun.
"""
from __future__ import annotations

from app.domain.models import CriterionScore, TopCandidate


def compute_average(scores: list[CriterionScore]) -> float:
    if not scores:
        return 0.0
    return round(sum(s.score for s in scores) / len(scores), 2)


def dynamic_scores_dict(scores: list[CriterionScore]) -> dict[str, int]:
    return {s.criterionLabel: s.score for s in scores}


def rank_top_n(candidates: list[TopCandidate], n: int = 3) -> list[TopCandidate]:
    """averageScore azalan, eşitlikte pdfFileName artan — deterministik sıralama."""
    ordered = sorted(candidates, key=lambda c: (-c.averageScore, c.pdfFileName))
    top = ordered[:n]
    return [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(top)]
