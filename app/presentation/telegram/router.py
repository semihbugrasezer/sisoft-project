"""Telegram Application kurulumu ve handler kaydı."""
from __future__ import annotations

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.container import Container
from app.presentation.telegram.handlers import (
    analyze_command,
    batch_command,
    cancel_command,
    criteria_command,
    criteria_show_command,
    document_message,
    error_handler,
    reset_command,
    start_command,
    text_message,
)


def build_application(token: str, container: Container) -> Application:
    async def _post_init(app: Application) -> None:
        # Terk edilmiş CV'leri açılışta temizle: kullanıcı /batch ile yükleyip hiç
        # /analyze veya /cancel yazmadıysa ya da süreç sert şekilde sonlandıysa
        # (finally çalışmaz) dosyalar SQLite'ta kalır. CV kişisel veridir —
        # süresiz saklanmamalı (bkz. SECURITY.md).
        hours = container.config.cv_retention_hours
        if hours > 0:
            await container.repo.purge_expired_pending_files(hours * 3600)

    async def _post_shutdown(app: Application) -> None:
        await container.llm.aclose()
        await container.repo.close()

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(8)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.bot_data["container"] = container

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("criteria", criteria_command))
    application.add_handler(CommandHandler("criteria_show", criteria_show_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(CommandHandler("batch", batch_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.Document.ALL, document_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_error_handler(error_handler)

    return application
