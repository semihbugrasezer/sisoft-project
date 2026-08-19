"""Ortam değişkenlerini tek yerden okur."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    telegram_token: str
    llm_backend: str
    ollama_base_url: str
    ollama_model: str
    ollama_intent_model: str | None
    ollama_max_concurrency: int
    llm_api_key: str | None
    db_path: str
    llm_timeout: float


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN .env dosyasında tanımlı değil. "
            ".env.example dosyasını .env olarak kopyalayıp token'ı ekleyin."
        )
    llm_backend = os.getenv("LLM_BACKEND", "ollama").strip().lower()
    if llm_backend not in ("ollama", "openai_compatible"):
        raise RuntimeError(
            f"LLM_BACKEND '{llm_backend}' geçersiz — 'ollama' veya 'openai_compatible' olmalı."
        )
    return Config(
        telegram_token=token,
        # 'ollama': OllamaClient, Ollama'nın kendi /api/chat'ini kullanır (varsayılan,
        # davranış değişmez). 'openai_compatible': OpenAICompatibleClient, /v1/chat/
        # completions üzerinden LM Studio, vLLM veya Ollama'nın kendi OpenAI-uyumlu
        # ucuyla konuşur — bkz. README.md → Tasarım Kararları.
        llm_backend=llm_backend,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        # İsteğe bağlı: her sohbet mesajında çalışan intent-classifier (kriter mi/sohbet
        # mi) için daha küçük/hızlı bir model, örn. "qwen2.5:1.5b". Boşsa ana model
        # kullanılır — davranış değişmez, yalnızca opt-in hızlanma.
        ollama_intent_model=os.getenv("OLLAMA_INTENT_MODEL") or None,
        # Tek yerel LLM instance'ına aynı anda gidebilecek istek sayısını sınırlar
        # (bkz. ollama_client.py / openai_compatible_client.py) — Telegram
        # concurrent_updates(8) sınırından bağımsız.
        ollama_max_concurrency=int(os.getenv("OLLAMA_MAX_CONCURRENCY", "3")),
        # openai_compatible backend'i için isteğe bağlı — LM Studio/vLLM lokal
        # kurulumda genelde gerekmez, uzak/korumalı bir uç için kullanılabilir.
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        db_path=os.getenv("DB_PATH", "sisoft.db"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "600")),
    )
