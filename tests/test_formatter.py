import json

from app.domain.models import CandidateProfile, EvaluationResult, MultiAnalysisResponse
from app.presentation.telegram.formatter import format_multi_analysis_json, format_single_analysis


def test_single_analysis_escapes_dynamic_markdown():
    report = format_single_analysis(
        CandidateProfile(
            candidateName="Ada_Test",
            contact={},
            summary=None,
            skills=[],
            workExperiences=[],
            education=[],
            languages=[],
        ),
        EvaluationResult(
            scores=[],
            strengths=["Python *ileri*"],
            weaknesses=[],
            recommendations=[],
            hrEvaluation="[uygun]",
        ),
    )
    assert "Ada\\_Test" in report
    assert "Python \\*ileri\\*" in report
    assert "\\[uygun]" in report


def test_multi_analysis_output_is_valid_json():
    output = format_multi_analysis_json(
        MultiAnalysisResponse(
            status="success",
            processedCVCount=0,
            userDefinedCriteria=[],
            topCandidates=[],
        )
    )
    assert json.loads(output)["status"] == "success"
