import pytest

from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


@pytest.mark.asyncio
async def test_complete_chat_history_persists_in_order(tmp_path):
    db_path = str(tmp_path / "chat.db")
    repo = SQLiteRepo(db_path)
    for index in range(20):
        await repo.add_message(7, "user", str(index))
    await repo.close()

    reopened = SQLiteRepo(db_path)
    messages = await reopened.get_messages(7)
    await reopened.close()

    assert [message["content"] for message in messages] == [str(index) for index in range(20)]
