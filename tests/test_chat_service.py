import asyncio

import pytest

from app.application.chat_service import ChatService


class FakeLLM:
    async def chat(self, messages):
        self.messages = messages
        return "yanıt"


class FakeRepo:
    def __init__(self):
        self.history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": str(index)}
            for index in range(20)
        ]
        self.added = []

    async def get_messages(self, chat_id):
        return self.history

    async def add_message(self, chat_id, role, content):
        self.added.append((chat_id, role, content))


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

        async def chat(self, messages):
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
