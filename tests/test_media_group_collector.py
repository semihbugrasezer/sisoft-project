import pytest

from app.presentation.telegram.media_group_collector import MediaGroupManager


@pytest.mark.asyncio
async def test_add_file_accumulates_until_limit():
    manager = MediaGroupManager()
    buf1, added1 = await manager.add_file(1, "g1", "a.pdf", b"a", max_files=5)
    buf2, added2 = await manager.add_file(1, "g1", "b.pdf", b"b", max_files=5)
    assert added1 and added2
    assert buf1 is buf2
    assert [f[0] for f in buf2.files] == ["a.pdf", "b.pdf"]


@pytest.mark.asyncio
async def test_add_file_rejects_beyond_limit():
    manager = MediaGroupManager()
    for i in range(5):
        _, added = await manager.add_file(1, "g1", f"{i}.pdf", b"x", max_files=5)
        assert added
    _, added_6th = await manager.add_file(1, "g1", "6.pdf", b"x", max_files=5)
    assert not added_6th


@pytest.mark.asyncio
async def test_different_groups_are_independent():
    manager = MediaGroupManager()
    await manager.add_file(1, "g1", "a.pdf", b"a", max_files=5)
    await manager.add_file(1, "g2", "b.pdf", b"b", max_files=5)
    buf1 = await manager.pop(1, "g1")
    buf2 = await manager.pop(1, "g2")
    assert [f[0] for f in buf1.files] == ["a.pdf"]
    assert [f[0] for f in buf2.files] == ["b.pdf"]


@pytest.mark.asyncio
async def test_pop_removes_buffer():
    manager = MediaGroupManager()
    await manager.add_file(1, "g1", "a.pdf", b"a", max_files=5)
    first = await manager.pop(1, "g1")
    second = await manager.pop(1, "g1")
    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_late_file_after_group_is_processed_is_rejected():
    # Regresyon: 5 dosya dolunca grup hemen işlenir (pop). Telegram'dan geç gelen
    # 6. update, pop sonrası setdefault ile YENİ bir arabellek yaratıp ayrı bir
    # batch gibi işlenebiliyordu.
    manager = MediaGroupManager()
    for index in range(5):
        _, added = await manager.add_file(1, "g1", f"{index}.pdf", b"x", 5)
        assert added

    popped = await manager.pop(1, "g1")
    assert popped is not None and len(popped.files) == 5

    _, added = await manager.add_file(1, "g1", "late.pdf", b"x", 5)
    assert not added, "kapatılmış gruba geç gelen dosya kabul edildi"


@pytest.mark.asyncio
async def test_new_group_after_close_still_works():
    # Kapatma yalnızca o group_id'yi etkilemeli; sonraki albümler çalışmalı.
    manager = MediaGroupManager()
    await manager.add_file(1, "g1", "a.pdf", b"x", 5)
    await manager.pop(1, "g1")

    _, added = await manager.add_file(1, "g2", "b.pdf", b"x", 5)
    assert added
