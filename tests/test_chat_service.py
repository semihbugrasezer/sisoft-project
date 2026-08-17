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
