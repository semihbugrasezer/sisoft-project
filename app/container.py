"""Bağımlılıkları tek yerde kurar (basit DI — framework yok, gerek de yok)."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.batch_analysis_service import BatchAnalysisService
from app.application.chat_service import ChatService
from app.application.criteria_service import CriteriaService
from app.application.cv_analysis_service import CVAnalysisService
from app.config import Config
from app.domain.ports import LLMPort
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.openai_compatible_client import OpenAICompatibleClient
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


@dataclass
class Container:
    config: Config
    llm: LLMPort
    repo: SQLiteRepo
    chat_service: ChatService
    criteria_service: CriteriaService
    cv_service: CVAnalysisService
    batch_service: BatchAnalysisService


def _build_llm(config: Config) -> LLMPort:
    """`LLM_BACKEND`'e göre Ollama'nın kendi /api/chat'i veya OpenAI-uyumlu
    /v1/chat/completions (LM Studio, vLLM, Ollama'nın kendi uyumlu ucu) seçilir."""
    if config.llm_backend == "openai_compatible":
        return OpenAICompatibleClient(
            config.ollama_base_url,
            config.ollama_model,
            config.llm_timeout,
            max_concurrency=config.ollama_max_concurrency,
            api_key=config.llm_api_key,
        )
    return OllamaClient(
        config.ollama_base_url,
        config.ollama_model,
        config.llm_timeout,
        max_concurrency=config.ollama_max_concurrency,
    )


def build_container(config: Config) -> Container:
    llm = _build_llm(config)
    repo = SQLiteRepo(config.db_path)
    cv_service = CVAnalysisService(llm)
    return Container(
        config=config,
        llm=llm,
        repo=repo,
        chat_service=ChatService(llm, repo),
        criteria_service=CriteriaService(llm, repo, intent_model=config.ollama_intent_model),
        cv_service=cv_service,
        batch_service=BatchAnalysisService(cv_service),
    )
