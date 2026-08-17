"""Telegram I/O katmanı. İş mantığı katmanlı backend servislerinde kalır (RULES.md §6)."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.domain.errors import AppError
from app.domain.models import MAX_CV_COUNT, Criterion
from app.presentation.telegram.formatter import (
    TELEGRAM_MAX_LEN,
    chunk_message,
    format_multi_analysis_json,
    format_single_analysis,
)
from app.presentation.telegram.media_group_collector import MediaGroupManager

logger = logging.getLogger(__name__)

MEDIA_GROUP_DEBOUNCE_SECONDS = 1.8

START_MESSAGE = (
    "Merhaba! Ben bir İK ve sohbet botuyum.\n\n"
    "- Benimle serbest sohbet edebilirsin, bağlamı hatırlarım.\n"
    "- Kriter tanımlamak için komuta gerek yok, doğrudan yaz:\n"
    "  \"CV'leri React tecrübesi, temiz kod ve uzaktan çalışma uyumuna göre değerlendir\"\n"
    "  (İstersen /criteria <serbest metin> ile de aynısını yapabilirsin.)\n"
    "- Kriter tanımlıyken PDF gönder:\n"
    "  • Tek PDF → hemen detaylı Markdown analiz raporu\n"
    "  • Aynı gönderimde albüm olarak 2-5 PDF → otomatik top-3 JSON\n"
    "  • Dosyaları tek tek göndermek istersen önce /batch, sonra PDF'ler, sonra /analyze\n"
    "- /criteria_show: aktif kriterleri gösterir\n"
    "- /cancel: bekleyen CV kuyruğunu temizler\n"
    "- /reset: sohbet geçmişini ve kriterleri sıfırlar"
)


def _container(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["container"]


def _chat_lock(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> asyncio.Lock:
    """chat_id bazlı lock: aynı sohbetin iki analizi çakışmasın (RULES.md §5)."""
    locks: dict[int, asyncio.Lock] = context.application.bot_data.setdefault("chat_locks", {})
    if chat_id not in locks:
        locks[chat_id] = asyncio.Lock()
    return locks[chat_id]


def _media_group_manager(context: ContextTypes.DEFAULT_TYPE) -> MediaGroupManager:
    return context.application.bot_data.setdefault("media_group_manager", MediaGroupManager())


def _batch_mode_chats(context: ContextTypes.DEFAULT_TYPE) -> set[int]:
    return context.application.bot_data.setdefault("batch_mode_chats", set())


async def _reply_criteria_saved(update: Update, criteria: list[Criterion]) -> None:
    lines = ["Aktif kriterler:"] + [f"{i + 1}. {c.label}" for i, c in enumerate(criteria)]
    lines.append(
        "\nŞimdi tek bir CV gönderebilir ya da albüm olarak en fazla 5 CV birden yükleyebilirsin."
    )
    await update.message.reply_text("\n".join(lines))


async def _process_files(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    files: list[tuple[str, bytes]],
    criteria: list[Criterion],
) -> None:
    """Tekli (1 dosya) veya çoklu (2-5 dosya) analiz akışını çalıştırır ve sonucu
    doğrudan context.bot ile gönderir — hem canlı update hem debounce task'ından
    çağrılabilir olması için update nesnesine bağımlı değildir."""
    container = _container(context)
    lock = _chat_lock(context, chat_id)
    async with lock:
        if len(files) == 1:
            filename, pdf_bytes = files[0]
            try:
                profile, evaluation = await container.cv_service.analyze(pdf_bytes, criteria)
            except AppError as exc:
                await context.bot.send_message(chat_id, exc.user_message)
                return
            report = format_single_analysis(profile, evaluation)
            for chunk in chunk_message(report):
                await context.bot.send_message(chat_id, chunk, parse_mode="Markdown")
            return

        try:
            response = await container.batch_service.analyze_batch(files, criteria)
        except AppError as exc:
            await context.bot.send_message(chat_id, exc.user_message)
            return

        result_json = format_multi_analysis_json(response)
        if len(result_json) <= TELEGRAM_MAX_LEN:
            await context.bot.send_message(chat_id, result_json)
        else:
            await context.bot.send_document(
                chat_id,
                document=result_json.encode("utf-8"),
                filename="top_candidates.json",
                caption="Top 3 aday sonucu",
            )


async def _debounce_and_trigger(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    group_id: str,
    criteria: list[Criterion],
    delay: float,
) -> None:
    if delay > 0:
        await asyncio.sleep(delay)
    buf = await _media_group_manager(context).pop(chat_id, group_id)
    if buf is None or not buf.files:
        return
    await context.bot.send_message(
        chat_id, f"{len(buf.files)} CV işleniyor, botu bu sırada kullanmaya devam edebilirsin..."
    )
    await _process_files(context, chat_id, buf.files, criteria)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_MESSAGE)


async def criteria_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    free_text = " ".join(context.args)
    if not free_text.strip():
        await update.message.reply_text(
            "Kullanım: /criteria React tecrübesi, temiz kod, uzaktan çalışma"
        )
        return

    try:
        criteria = await _container(context).criteria_service.define_criteria(chat_id, free_text)
    except AppError as exc:
        await update.message.reply_text(exc.user_message)
        return
    await _reply_criteria_saved(update, criteria)


async def criteria_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        criteria = await _container(context).criteria_service.get_active_criteria(chat_id)
    except AppError as exc:
        await update.message.reply_text(exc.user_message)
        return

    lines = ["Aktif kriterler:"] + [f"{i + 1}. {c.label}" for i, c in enumerate(criteria)]
    await update.message.reply_text("\n".join(lines))


async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dosyaları albüm yerine tek tek göndermek isteyenler için yedek akış."""
    chat_id = update.effective_chat.id
    _batch_mode_chats(context).add(chat_id)
    await update.message.reply_text(
        "Toplu mod açık. PDF'leri tek tek gönderebilirsin, bitince /analyze yaz."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _container(context).repo.clear_pending_files(chat_id)
    _batch_mode_chats(context).discard(chat_id)
    await update.message.reply_text("Bekleyen CV kuyruğu temizlendi.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _container(context)
    await container.repo.clear_history(chat_id)
    await container.repo.clear_criteria(chat_id)
    await container.repo.clear_pending_files(chat_id)
    _batch_mode_chats(context).discard(chat_id)
    await update.message.reply_text("Sohbet geçmişi ve kriterler sıfırlandı.")


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text
    container = _container(context)

    try:
        criteria = await container.criteria_service.define_if_requested(chat_id, text)
    except AppError as exc:
        await update.message.reply_text(exc.user_message)
        return
    if criteria is not None:
        await _reply_criteria_saved(update, criteria)
        return

    try:
        reply = await container.chat_service.reply(chat_id, text)
    except AppError as exc:
        await update.message.reply_text(exc.user_message)
        return
    await update.message.reply_text(reply)


async def document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _container(context)
    document = update.message.document

    if not document.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("Sadece PDF dosyaları kabul edilir.")
        return

    # PDF caption'ında kriter cümlesi varsa önce onu kaydet (RULES.md §3).
    caption = update.message.caption
    if caption:
        try:
            await container.criteria_service.define_if_requested(chat_id, caption)
        except AppError as exc:
            await update.message.reply_text(exc.user_message)
            return

    try:
        criteria = await container.criteria_service.get_active_criteria(chat_id)
    except AppError as exc:
        await update.message.reply_text(exc.user_message)
        return

    tg_file = await document.get_file()
    pdf_bytes = bytes(await tg_file.download_as_bytearray())

    media_group_id = update.message.media_group_id
    if media_group_id:
        manager = _media_group_manager(context)
        buf, added = await manager.add_file(
            chat_id, media_group_id, document.file_name, pdf_bytes, MAX_CV_COUNT
        )
        if not added:
            await update.message.reply_text(
                f"En fazla {MAX_CV_COUNT} CV yükleyebilirsiniz, "
                f"bu dosya atlandı: {document.file_name}"
            )
            return

        if buf.timer_task and not buf.timer_task.done():
            buf.timer_task.cancel()

        if len(buf.files) >= MAX_CV_COUNT:
            buf.timer_task = context.application.create_task(
                _debounce_and_trigger(context, chat_id, media_group_id, criteria, delay=0)
            )
        else:
            buf.timer_task = context.application.create_task(
                _debounce_and_trigger(
                    context, chat_id, media_group_id, criteria, delay=MEDIA_GROUP_DEBOUNCE_SECONDS
                )
            )
        return

    if chat_id in _batch_mode_chats(context):
        pending_count = await container.repo.count_pending_files(chat_id)
        if pending_count >= MAX_CV_COUNT:
            await update.message.reply_text(
                f"En fazla {MAX_CV_COUNT} CV yükleyebilirsiniz. "
                "/analyze ile başlatın veya /cancel ile temizleyin."
            )
            return
        await container.repo.add_pending_file(chat_id, document.file_name, pdf_bytes)
        new_count = pending_count + 1
        await update.message.reply_text(
            f"{document.file_name} kuyruğa eklendi ({new_count}/{MAX_CV_COUNT}). "
            "Analizi başlatmak için /analyze yazın."
        )
        return

    # Albümsüz, toplu mod değil: tek dosya, hemen işlenir.
    await update.message.reply_text(
        "CV analiz ediliyor; yerel modelin hızına göre birkaç dakika sürebilir..."
    )
    await _process_files(context, chat_id, [(document.file_name, pdf_bytes)], criteria)


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _container(context)

    files = await container.repo.get_pending_files(chat_id)
    if not files:
        await update.message.reply_text(
            "Kuyrukta CV yok. /batch ile toplu mod açıp PDF gönderin, "
            "ya da PDF'leri albüm olarak birlikte seçip gönderin."
        )
        return

    try:
        criteria = await container.criteria_service.get_active_criteria(chat_id)
    except AppError as exc:
        await update.message.reply_text(exc.user_message)
        return

    _batch_mode_chats(context).discard(chat_id)
    await update.message.reply_text(
        f"{len(files)} CV işleniyor, botu bu sırada kullanmaya devam edebilirsin..."
    )
    await _process_files(context, chat_id, files, criteria)
    await container.repo.clear_pending_files(chat_id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Beklenmeyen hata", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Beklenmeyen bir hata oluştu, lütfen tekrar deneyin."
        )
