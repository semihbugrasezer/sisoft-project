import asyncio

import pytest

from app.application.chat_service import ChatService


class FakeLLM:
    async def chat(self, messages, temperature=0.7):
        self.messages = messages
        return "yanıt"


class FakeRepo:
    """Bağlam penceresi taşmayan (özet gerektirmeyen) sohbet."""

    def __init__(self):
        self.history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": str(index)}
            for index in range(20)
        ]
        self.added = []
        self.summary = None

    async def get_messages(self, chat_id):
        return self.history

    async def add_message(self, chat_id, role, content):
        self.added.append((chat_id, role, content))

    async def get_summary(self, chat_id):
        return self.summary

    async def get_unsummarized_overflow(self, chat_id, limit):
        return []

    async def set_summary(self, chat_id, summary, last_summarized_id):
        self.summary = summary


@pytest.mark.asyncio
async def test_reply_passes_complete_persisted_history_to_model():
    llm = FakeLLM()
    repo = FakeRepo()

    reply = await ChatService(llm, repo).reply(7, "yeni mesaj")

    assert reply == "yanıt"
    assert llm.messages[1:-1] == repo.history
    assert repo.added == [(7, "user", "yeni mesaj"), (7, "assistant", "yanıt")]


@pytest.mark.asyncio
async def test_same_chat_messages_are_serialized_with_updated_context():
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class SlowLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, messages, temperature=0.7):
            self.calls.append(messages)
            if len(self.calls) == 1:
                first_started.set()
                await release_first.wait()
            return f"yanıt-{len(self.calls)}"

    class MemoryRepo:
        def __init__(self):
            self.history = []

        async def get_messages(self, chat_id):
            return list(self.history)

        async def add_message(self, chat_id, role, content):
            self.history.append({"role": role, "content": content})

        async def get_summary(self, chat_id):
            return None

        async def get_unsummarized_overflow(self, chat_id, limit):
            return []

        async def set_summary(self, chat_id, summary, last_summarized_id):
            pass

    llm = SlowLLM()
    service = ChatService(llm, MemoryRepo())
    first = asyncio.create_task(service.reply(7, "birinci"))
    await first_started.wait()
    second = asyncio.create_task(service.reply(7, "ikinci"))
    await asyncio.sleep(0)
    release_first.set()
    await asyncio.gather(first, second)

    assert llm.calls[1][1:3] == [
        {"role": "user", "content": "birinci"},
        {"role": "assistant", "content": "yanıt-1"},
    ]


# --- rolling summary: pencere dışına taşan bağlam kaybolmamalı ----------------


class SummaryRepo:
    """Pencere dışına taşmış, henüz özetlenmemiş mesajları olan sohbet."""

    def __init__(self, overflow, existing_summary=None):
        self._overflow = overflow
        self.summary = existing_summary
        self.summarized_upto = None
        self.history = [{"role": "user", "content": "son mesaj"}]

    async def get_messages(self, chat_id):
        return self.history

    async def add_message(self, chat_id, role, content):
        pass

    async def get_summary(self, chat_id):
        return self.summary

    async def get_unsummarized_overflow(self, chat_id, limit):
        return self._overflow

    async def set_summary(self, chat_id, summary, last_summarized_id):
        self.summary = summary
        self.summarized_upto = last_summarized_id


@pytest.mark.asyncio
async def test_overflow_is_folded_into_summary_and_injected_into_system_prompt():
    class SummarizingLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, messages, temperature=0.7):
            self.calls.append(messages)
            if len(self.calls) == 1:  # özetleme çağrısı
                return "Kullanıcının adı Semih, Python üzerine konuşuluyor."
            return "yanıt"

    repo = SummaryRepo(
        overflow=[
            {"id": 1, "role": "user", "content": "benim adım Semih"},
            {"id": 2, "role": "assistant", "content": "memnun oldum"},
        ]
    )
    llm = SummarizingLLM()

    await ChatService(llm, repo).reply(7, "adım neydi?")

    # eski bağlam özete katlandı ve ilerleme kaydedildi
    assert repo.summary == "Kullanıcının adı Semih, Python üzerine konuşuluyor."
    assert repo.summarized_upto == 2
    # özetlenecek ham mesajlar gerçekten özetleyiciye gitti
    assert "benim adım Semih" in llm.calls[0][1]["content"]
    # ve özet, asıl sohbet çağrısının system prompt'una enjekte edildi
    assert "Kullanıcının adı Semih" in llm.calls[1][0]["content"]


@pytest.mark.asyncio
async def test_existing_summary_is_passed_to_summarizer_for_folding():
    class EchoLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, messages, temperature=0.7):
            self.calls.append(messages)
            return "güncellenmiş özet"

    repo = SummaryRepo(
        overflow=[{"id": 5, "role": "user", "content": "yeni konu"}],
        existing_summary="eski özet metni",
    )

    await ChatService(EchoLLM(), repo).reply(7, "devam")

    assert repo.summary == "güncellenmiş özet"
    assert repo.summarized_upto == 5


@pytest.mark.asyncio
async def test_summarizer_failure_does_not_break_chat_or_lose_data():
    """Özetleme başarısız olursa sohbet devam eder; last_summarized_id ilerlemediği
    için aynı mesajlar bir sonraki turda tekrar özetlenmeye çalışılır (veri kaybı yok)."""

    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, temperature=0.7):
            self.calls += 1
            if self.calls == 1:  # özetleme çağrısı patlar
                raise RuntimeError("model down")
            return "yanıt"

    repo = SummaryRepo(overflow=[{"id": 9, "role": "user", "content": "x"}])

    reply = await ChatService(FlakyLLM(), repo).reply(7, "merhaba")

    assert reply == "yanıt"
    assert repo.summary is None
    assert repo.summarized_upto is None
