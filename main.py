"""Entrypoint: config yükle, container kur, Telegram polling başlat."""
import logging

from app.config import load_config
from app.container import build_container
from app.presentation.telegram.router import build_application

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    config = load_config()
    container = build_container(config)
    application = build_application(config.telegram_token, container)
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
