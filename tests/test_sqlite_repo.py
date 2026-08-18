import pytest

from app.infrastructure.persistence.sqlite_repo import CHAT_HISTORY_LIMIT, SQLiteRepo


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


@pytest.mark.asyncio
async def test_order_survives_identical_timestamps(tmp_path, monkeypatch):
    """Aynı time.time() tick'ine denk gelen user/assistant çifti `id` sırasıyla
    (rowid, monotonik) döner — `ts` ile sıralansaydı sıra tanımsız olurdu."""
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    monkeypatch.setattr(
        "app.infrastructure.persistence.sqlite_repo.time.time", lambda: 1000.0
    )
    await repo.add_message(1, "user", "soru")
    await repo.add_message(1, "assistant", "cevap")
    await repo.close()

    reopened = SQLiteRepo(str(tmp_path / "chat.db"))
    messages = await reopened.get_messages(1)
    await reopened.close()

    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "soru"),
        ("assistant", "cevap"),
    ]


@pytest.mark.asyncio
async def test_chat_history_is_capped_to_limit(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    total = CHAT_HISTORY_LIMIT + 10
    for index in range(total):
        await repo.add_message(3, "user", str(index))

    messages = await repo.get_messages(3)
    await repo.close()

    assert len(messages) == CHAT_HISTORY_LIMIT
    # en eski mesajlar atılır, kalanlar kronolojik sırayı korur
    expected_start = total - CHAT_HISTORY_LIMIT
    assert [m["content"] for m in messages] == [str(i) for i in range(expected_start, total)]


@pytest.mark.asyncio
async def test_try_add_pending_file_enforces_limit_atomically(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    for index in range(5):
        added = await repo.try_add_pending_file(1, f"cv{index}.pdf", b"x", limit=5)
        assert added is True

    rejected = await repo.try_add_pending_file(1, "cv6.pdf", b"x", limit=5)
    await repo.close()

    assert rejected is False
