import pytest

from app.config import load_config


def _set_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")


def test_defaults_to_ollama_backend(monkeypatch):
    _set_token(monkeypatch)
    monkeypatch.delenv("LLM_BACKEND", raising=False)

    config = load_config()

    assert config.llm_backend == "ollama"


def test_accepts_openai_compatible_backend(monkeypatch):
    _set_token(monkeypatch)
    monkeypatch.setenv("LLM_BACKEND", "openai_compatible")

    config = load_config()

    assert config.llm_backend == "openai_compatible"


def test_backend_value_is_case_insensitive(monkeypatch):
    _set_token(monkeypatch)
    monkeypatch.setenv("LLM_BACKEND", "OpenAI_Compatible")

    config = load_config()

    assert config.llm_backend == "openai_compatible"


def test_rejects_unknown_backend(monkeypatch):
    _set_token(monkeypatch)
    monkeypatch.setenv("LLM_BACKEND", "vllm-direct")

    with pytest.raises(RuntimeError, match="LLM_BACKEND"):
        load_config()


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        load_config()
