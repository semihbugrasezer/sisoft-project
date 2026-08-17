from types import SimpleNamespace

from app.presentation.telegram.router import build_application


def test_application_processes_updates_concurrently():
    application = build_application("123:ABC", SimpleNamespace(llm=None, repo=None))
    assert application.update_processor.max_concurrent_updates > 1
