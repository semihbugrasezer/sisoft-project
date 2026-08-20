from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from app.domain.models import (
    CandidateProfile,
    Contact,
    Criterion,
    CriterionScore,
    EvaluationResult,
    MultiAnalysisResponse,
    TopCandidate,
)
from app.presentation.telegram.handlers import _process_files


@pytest.mark.asyncio
async def test_oversized_top_three_json_is_sent_as_one_document():
    response = MultiAnalysisResponse(
        status="success",
        processedCVCount=2,
        userDefinedCriteria=["React"],
        topCandidates=[
            TopCandidate(
                rank=1,
                candidateName="Ada",
                pdfFileName="ada.pdf",
                dynamicScores={"React": 90},
                averageScore=90,
                hrEvaluation="x" * 5000,
            )
        ],
    )

    class BatchService:
        async def analyze_batch(self, files, criteria):
            return response

    class Bot:
        def __init__(self):
            self.messages = []
            self.documents = []

        async def send_message(self, *args, **kwargs):
            self.messages.append((args, kwargs))

        async def send_document(self, *args, **kwargs):
            self.documents.append((args, kwargs))

    bot = Bot()
    context = SimpleNamespace(
        bot=bot,
        application=SimpleNamespace(
            bot_data={"container": SimpleNamespace(batch_service=BatchService())}
        ),
    )
    criteria = [Criterion(id="react", label="React", description="x")]

    await _process_files(context, 7, [("a.pdf", b"a"), ("b.pdf", b"b")], criteria)

    assert not bot.messages
    assert len(bot.documents) == 1
    assert bot.documents[0][1]["filename"] == "top_candidates.json"
    assert bot.documents[0][1]["document"].startswith(b"{")


@pytest.mark.asyncio
async def test_single_analysis_report_falls_back_to_plain_text_on_bad_markdown():
    # Gerçek Telegram testinde /start mesajındaki eşleşmeyen bir '_' Telegram'ın
    # legacy Markdown ayrıştırıcısını kırıp BadRequest fırlattı ve kullanıcı raporu
    # hiç göremedi. CV analiz raporu LLM tarafından üretildiği için dengeli
    # markdown garanti edilemez; parse_mode="Markdown" başarısız olursa düz metne
    # düşülmeli, mesaj kaybolmamalı.
    profile = CandidateProfile(
        candidateName="Ada",
        contact=Contact(),
        summary=None,
        skills=["React"],
        workExperiences=[],
        education=[],
        languages=[],
    )
    evaluation = EvaluationResult(
        scores=[
            CriterionScore(
                criterionId="react",
                criterionLabel="React",
                score=90,
                evidence=["5 yıl React deneyimi"],
                reason="x",
            )
        ],
        strengths=["x"],
        weaknesses=["x"],
        recommendations=["x"],
        hrEvaluation="Güçlü aday",
    )

    class CvService:
        async def analyze(self, pdf_bytes, criteria):
            return profile, evaluation

    class Bot:
        def __init__(self):
            self.messages = []

        async def send_message(self, chat_id, text, parse_mode=None):
            if parse_mode is not None:
                raise BadRequest("Can't parse entities: can't find end of the entity")
            self.messages.append(text)

    bot = Bot()
    context = SimpleNamespace(
        bot=bot,
        application=SimpleNamespace(
            bot_data={"container": SimpleNamespace(cv_service=CvService())}
        ),
    )
    criteria = [Criterion(id="react", label="React", description="x")]

    await _process_files(context, 7, [("a.pdf", b"a")], criteria)

    assert bot.messages  # düz metne düşerek rapor yine de teslim edildi
    assert "Güçlü aday" in bot.messages[0]
