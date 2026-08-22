"""Domain skorlama mantığı için minimal testler — LLM/Telegram'sız, saf fonksiyonlar."""
from app.domain.models import CriterionScore, TopCandidate
from app.domain.scoring import compute_average, dynamic_scores_dict, rank_top_n


def test_compute_average_rounds_to_two_decimals():
    scores = [
        CriterionScore(criterionId="a", criterionLabel="A", score=95, evidenceIds=["x"], reason="x"),
        CriterionScore(criterionId="b", criterionLabel="B", score=85, evidenceIds=["x"], reason="x"),
        CriterionScore(criterionId="c", criterionLabel="C", score=90, evidenceIds=["x"], reason="x"),
    ]
    assert compute_average(scores) == 90.0


def test_compute_average_empty_is_zero():
    assert compute_average([]) == 0.0


def test_dynamic_scores_dict_maps_label_to_score():
    scores = [
        CriterionScore(
            criterionId="a", criterionLabel="React", score=70, evidenceIds=["x"], reason="x"
        )
    ]
    assert dynamic_scores_dict(scores) == {"React": 70}


def _candidate(name: str, avg: float) -> TopCandidate:
    return TopCandidate(
        rank=0, candidateName=name, pdfFileName=f"{name}.pdf",
        dynamicScores={}, averageScore=avg, hrEvaluation="",
    )


def test_rank_top_n_orders_by_average_desc_and_assigns_rank():
    candidates = [_candidate("c", 70), _candidate("a", 90), _candidate("b", 80), _candidate("d", 60)]
    top = rank_top_n(candidates, n=3)
    assert [c.candidateName for c in top] == ["a", "b", "c"]
    assert [c.rank for c in top] == [1, 2, 3]


def test_rank_top_n_tie_break_by_filename_ascending():
    candidates = [_candidate("z", 80), _candidate("a", 80)]
    top = rank_top_n(candidates, n=3)
    assert [c.candidateName for c in top] == ["a", "z"]


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
