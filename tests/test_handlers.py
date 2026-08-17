from types import SimpleNamespace

import pytest

from app.domain.models import Criterion, MultiAnalysisResponse, TopCandidate
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
