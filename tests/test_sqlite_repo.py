import time

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
async def test_overflow_excludes_recent_window_and_already_summarized(tmp_path):
    """Rolling summary'nin SQL'i: pencere içindeki son N mesaj ve daha önce
    özetlenmiş olanlar tekrar özetlenmeye gönderilmez."""
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    total = CHAT_HISTORY_LIMIT + 6
    for index in range(total):
        await repo.add_message(4, "user", str(index))

    overflow = await repo.get_unsummarized_overflow(4, CHAT_HISTORY_LIMIT)
    # pencere dışında kalan 6 mesaj (en eskiler)
    assert [item["content"] for item in overflow] == [str(i) for i in range(6)]

    # ilk 3'ünü özetlenmiş işaretle → sadece kalan 3'ü dönmeli
    await repo.set_summary(4, "özet", overflow[2]["id"])
    remaining = await repo.get_unsummarized_overflow(4, CHAT_HISTORY_LIMIT)
    await repo.close()

    assert [item["content"] for item in remaining] == ["3", "4", "5"]


@pytest.mark.asyncio
async def test_no_overflow_before_window_is_full(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    for index in range(CHAT_HISTORY_LIMIT):
        await repo.add_message(4, "user", str(index))

    overflow = await repo.get_unsummarized_overflow(4, CHAT_HISTORY_LIMIT)
    await repo.close()

    assert overflow == []


@pytest.mark.asyncio
async def test_clear_history_also_clears_summary(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    await repo.add_message(4, "user", "x")
    await repo.set_summary(4, "eski özet", 1)

    await repo.clear_history(4)
    summary = await repo.get_summary(4)
    await repo.close()

    assert summary is None


@pytest.mark.asyncio
async def test_try_add_pending_file_enforces_limit_atomically(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    for index in range(5):
        added = await repo.try_add_pending_file(1, f"cv{index}.pdf", b"x", limit=5)
        assert added is True

    rejected = await repo.try_add_pending_file(1, "cv6.pdf", b"x", limit=5)
    await repo.close()

    assert rejected is False


@pytest.mark.asyncio
async def test_take_pending_files_claims_snapshot_atomically(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "chat.db"))
    await repo.add_pending_file(1, "a.pdf", b"a")
    await repo.add_pending_file(1, "b.pdf", b"b")

    first, second = await __import__("asyncio").gather(
        repo.take_pending_files(1),
        repo.take_pending_files(1),
    )

    await repo.add_pending_file(1, "new.pdf", b"new")
    remaining = await repo.get_pending_files(1)
    await repo.close()

    assert sorted((first, second), key=len) == [[], [("a.pdf", b"a"), ("b.pdf", b"b")]]
    assert remaining == [("new.pdf", b"new")]


@pytest.mark.asyncio
async def test_purge_expired_pending_files_removes_only_old_entries(tmp_path):
    # CV kişisel veridir: /batch ile yüklenip hiç /analyze edilmemiş dosyalar
    # süresiz kalmamalı (bkz. SECURITY.md).
    repo = SQLiteRepo(str(tmp_path / "t.db"))
    await repo.add_pending_file(1, "eski.pdf", b"a")
    await repo.add_pending_file(1, "yeni.pdf", b"b")

    # "eski.pdf" kaydını 48 saat geriye al.
    repo._conn.execute(
        "UPDATE pending_files SET ts = ? WHERE filename = ?",
        (time.time() - 48 * 3600, "eski.pdf"),
    )
    repo._conn.commit()

    deleted = await repo.purge_expired_pending_files(24 * 3600)

    assert deleted == 1
    remaining = await repo.get_pending_files(1)
    assert [name for name, _ in remaining] == ["yeni.pdf"]
    await repo.close()


@pytest.mark.asyncio
async def test_purge_keeps_everything_when_nothing_is_expired(tmp_path):
    repo = SQLiteRepo(str(tmp_path / "t2.db"))
    await repo.add_pending_file(1, "a.pdf", b"a")

    assert await repo.purge_expired_pending_files(24 * 3600) == 0
    assert len(await repo.get_pending_files(1)) == 1
    await repo.close()
