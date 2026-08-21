from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.presentation.telegram.router import build_application


def test_application_processes_updates_concurrently():
    application = build_application("123:ABC", SimpleNamespace(llm=None, repo=None))
    assert application.update_processor.max_concurrent_updates > 1


@pytest.mark.asyncio
async def test_post_init_purges_expired_chat_history_and_pending_cvs():
    repo = SimpleNamespace(
        purge_expired_chat_history=AsyncMock(),
        purge_expired_pending_files=AsyncMock(),
    )
    container = SimpleNamespace(
        config=SimpleNamespace(chat_retention_hours=168, cv_retention_hours=24),
        repo=repo,
        llm=None,
    )
    application = build_application("123:ABC", container)

    await application.post_init(application)

    repo.purge_expired_chat_history.assert_awaited_once_with(168 * 3600)
    repo.purge_expired_pending_files.assert_awaited_once_with(24 * 3600)
