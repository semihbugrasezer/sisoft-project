import json

from app.domain.models import (
    CandidateProfile,
    EvaluationResult,
    MultiAnalysisResponse,
    TopCandidate,
)
from app.presentation.telegram.formatter import (
    chunk_message,
    format_multi_analysis_json,
    format_single_analysis,
)


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
    # Gerçekçi minimum: batch en az 1 CV ve en az 1 kriterle çalışır — şema da
    # bunu zorunlu kılar (processedCVCount>=1, userDefinedCriteria min_length=1).
    output = format_multi_analysis_json(
        MultiAnalysisResponse(
            status="success",
            processedCVCount=1,
            userDefinedCriteria=["React"],
            topCandidates=[
                TopCandidate(
                    rank=1,
                    candidateName="Ada",
                    pdfFileName="ada.pdf",
                    dynamicScores={"React": 90},
                    averageScore=90.0,
                    hrEvaluation="uygun",
                )
            ],
        )
    )
    parsed = json.loads(output)
    assert parsed["status"] == "success"
    assert parsed["topCandidates"][0]["rank"] == 1


def test_markdown_chunks_prefer_line_boundaries():
    chunks = chunk_message("*Başlık*\n" + "satır\n" * 10, limit=20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert chunks[0].endswith("satır")
