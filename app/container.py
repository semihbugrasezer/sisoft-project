"""Bağımlılıkları tek yerde kurar (basit DI — framework yok, gerek de yok)."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.batch_analysis_service import BatchAnalysisService
from app.application.chat_service import ChatService
from app.application.criteria_service import CriteriaService
from app.application.cv_analysis_service import CVAnalysisService
from app.config import Config
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.persistence.sqlite_repo import SQLiteRepo


@dataclass
class Container:
    config: Config
    llm: OllamaClient
    repo: SQLiteRepo
    chat_service: ChatService
    criteria_service: CriteriaService
    cv_service: CVAnalysisService
    batch_service: BatchAnalysisService


def build_container(config: Config) -> Container:
    llm = OllamaClient(config.ollama_base_url, config.ollama_model, config.llm_timeout)
    repo = SQLiteRepo(config.db_path)
    cv_service = CVAnalysisService(llm)
    return Container(
        config=config,
        llm=llm,
        repo=repo,
        chat_service=ChatService(llm, repo, config.history_limit),
        criteria_service=CriteriaService(llm, repo),
        cv_service=cv_service,
        batch_service=BatchAnalysisService(cv_service, max_concurrency=2),
    )
