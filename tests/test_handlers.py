import asyncio
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
from app.presentation.telegram.handlers import _process_files, text_message


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
            return response, []

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
            return profile, evaluation, False

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


@pytest.mark.asyncio
async def test_single_analysis_warns_user_when_extracted_text_was_truncated():
    profile = CandidateProfile(
        candidateName="Ada", contact=Contact(), summary=None, skills=[],
        workExperiences=[], education=[], languages=[],
    )
    evaluation = EvaluationResult(
        scores=[CriterionScore(criterionId="react", criterionLabel="React", score=90,
                                evidence=["x"], reason="x")],
        strengths=["x"], weaknesses=["x"], recommendations=["x"], hrEvaluation="iyi",
    )

    class CvService:
        async def analyze(self, pdf_bytes, criteria):
            return profile, evaluation, True  # truncated=True

    class Bot:
        def __init__(self):
            self.messages = []

        async def send_message(self, chat_id, text, parse_mode=None):
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

    assert "kısaltıldı" in bot.messages[0]  # rapordan önce kırpma uyarısı geldi
    assert "iyi" in bot.messages[1]  # rapor yine de teslim edildi


def _text_update(chat_id: int, text: str, replies: list[str]):
    async def reply_text(message, **kwargs):
        replies.append(message)

    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        message=SimpleNamespace(text=text, reply_text=reply_text),
    )


class _OrderRecordingContainer:
    """Niyet sınıflandırmasını (yavaş) ve sohbet yanıtını (hızlı) taklit eder ve
    her adımın hangi sırada çalıştığını kaydeder."""

    def __init__(self, order: list[str]):
        self.order = order
        outer = self

        class CriteriaService:
            async def define_if_requested(self, chat_id, text):
                outer.order.append(f"intent:{text}")
                await asyncio.sleep(0.02)  # LLM çağrısı — yavaş adım
                return None  # "chat" niyeti

        class ChatService:
            async def reply(self, chat_id, text):
                outer.order.append(f"reply:{text}")
                return f"yanıt:{text}"

        self.criteria_service = CriteriaService()
        self.chat_service = ChatService()


@pytest.mark.asyncio
async def test_same_chat_messages_are_processed_in_arrival_order():
    # concurrent_updates(8) altında aynı sohbetten hızlıca gelen iki mesaj
    # eşzamanlı işlenmeye başlar. Niyet sınıflandırması kilit dışında kalsaydı
    # B'nin sınıflandırması A'dan önce bitip B önce ChatService.reply()'a
    # girebilir ve sohbet geçmişi ters sırada yazılabilirdi.
    order: list[str] = []
    replies: list[str] = []
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"container": _OrderRecordingContainer(order)})
    )

    await asyncio.gather(
        text_message(_text_update(1, "A", replies), context),
        text_message(_text_update(1, "B", replies), context),
    )

    # A tamamen bitmeden B başlamamalı (iç içe geçme yok)
    assert order in (
        ["intent:A", "reply:A", "intent:B", "reply:B"],
        ["intent:B", "reply:B", "intent:A", "reply:A"],
    ), order


@pytest.mark.asyncio
async def test_different_chats_are_not_serialized_against_each_other():
    # Farklı sohbetler birbirini beklememeli — aksi halde bir sohbetin uzun
    # analizi tüm botu kilitlerdi.
    order: list[str] = []
    replies: list[str] = []
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"container": _OrderRecordingContainer(order)})
    )

    await asyncio.gather(
        text_message(_text_update(1, "A", replies), context),
        text_message(_text_update(2, "B", replies), context),
    )

    # İkisi de yavaş intent adımına girmiş olmalı (araya girme = paralellik)
    assert order[0].startswith("intent:")
    assert order[1].startswith("intent:")
    assert len(replies) == 2
