"""Ortam değişkenlerini tek yerden okur."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    telegram_token: str
    ollama_base_url: str
    ollama_model: str
    db_path: str
    llm_timeout: float


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN .env dosyasında tanımlı değil. "
            ".env.example dosyasını .env olarak kopyalayıp token'ı ekleyin."
        )
    return Config(
        telegram_token=token,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        db_path=os.getenv("DB_PATH", "sisoft.db"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "600")),
    )
