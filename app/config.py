"""Ortam değişkenlerini tek yerden okur."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    telegram_token: str
    llm_backend: str
    llm_base_url: str
    llm_model: str
    llm_intent_model: str | None
    llm_max_concurrency: int
    llm_context_length: int
    llm_api_key: str | None
    db_path: str
    llm_timeout: float
    chat_retention_hours: float
    cv_retention_hours: float


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
        # ucuyla konuşur — bkz. docs/ARCHITECTURE.md. Değişken adları jenerik
        # (LLM_*) tutulur çünkü ikisi de aynı üç değeri (adres/model/eşzamanlılık)
        # kullanır; LM Studio/vLLM kullanırken "OLLAMA_..." adı kafa karıştırırdı.
        llm_backend=llm_backend,
        llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
        llm_model=os.getenv("LLM_MODEL", "qwen2.5:7b"),
        # İsteğe bağlı: her sohbet mesajında çalışan intent-classifier (kriter mi/sohbet
        # mi) için daha küçük/hızlı bir model, örn. "qwen2.5:1.5b". Boşsa ana model
        # kullanılır — davranış değişmez, yalnızca opt-in hızlanma.
        llm_intent_model=os.getenv("LLM_INTENT_MODEL") or None,
        # Tek yerel LLM instance'ına aynı anda gidebilecek istek sayısını sınırlar
        # (bkz. ollama_client.py / openai_compatible_client.py) — Telegram
        # concurrent_updates(8) sınırından bağımsız.
        llm_max_concurrency=int(os.getenv("LLM_MAX_CONCURRENCY", "3")),
        # Ollama'ya açıkça bildirilen context penceresi. Gönderilmezse Ollama kendi
        # varsayılanına (tipik 4096) düşer ve 5 CV'lik batch üretim sırasında taşar
        # (bkz. ollama_client.py). qwen2.5:7b 32k destekliyor; daha kısa context'li
        # bir model kullanılırsa bu değer düşürülmeli.
        llm_context_length=int(os.getenv("LLM_CONTEXT_LENGTH", "32768")),
        # openai_compatible backend'i için isteğe bağlı — LM Studio/vLLM lokal
        # kurulumda genelde gerekmez, uzak/korumalı bir uç için kullanılabilir.
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        db_path=os.getenv("DB_PATH", "sisoft.db"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "1200")),
        # Sohbet mesajları ve bunları içerebilecek rolling summary açılışta bu
        # yaştan sonra silinir. 0 veya negatif değer temizliği devre dışı bırakır.
        chat_retention_hours=float(os.getenv("CHAT_RETENTION_HOURS", "168")),
        # Bekleyen (henüz /analyze edilmemiş) CV'ler için AÇILIŞ temizliği yaş
        # eşiği. Temizlik yalnız post_init'te çalışır; kesintisiz çalışan bir botta
        # gerçek üst sınır değildir (bilinçli tercih — periyodik bir scheduler bu
        # ölçekte karşılıksız). CV kişisel veridir, bkz. SECURITY.md.
        # 0 veya negatif değer temizliği devre dışı bırakır.
        cv_retention_hours=float(os.getenv("CV_RETENTION_HOURS", "24")),
    )
