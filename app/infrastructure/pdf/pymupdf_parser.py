"""PDF doğrulama + metin çıkarma (RULES.md §4)."""
from __future__ import annotations

import pymupdf as fitz

from app.domain.errors import PDFValidationError

MAX_SIZE_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30
MIN_TEXT_CHARS = 100


def validate_and_extract_text(pdf_bytes: bytes) -> str:
    """Bozuk/şifreli/boş PDF'i sade Türkçe hata mesajıyla reddeder, geçerliyse metni döner."""
    if not pdf_bytes:
        raise PDFValidationError("Dosya boş görünüyor.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PDFValidationError("Dosya geçerli bir PDF değil.")
    if len(pdf_bytes) > MAX_SIZE_BYTES:
        raise PDFValidationError("PDF çok büyük (limit 10MB).")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFValidationError("PDF açılamadı, dosya bozuk olabilir.") from exc

    try:
        if doc.is_encrypted:
            raise PDFValidationError("PDF şifreli; lütfen şifresiz bir kopya yükleyin.")
        if doc.page_count == 0 or doc.page_count > MAX_PAGES:
            raise PDFValidationError(f"Sayfa sayısı desteklenmiyor (1-{MAX_PAGES} arası olmalı).")

        text = "\n".join(page.get_text(sort=True) for page in doc)
    finally:
        doc.close()

    if len(text.strip()) < MIN_TEXT_CHARS:
        raise PDFValidationError(
            "PDF açıldı ama okunabilir metin bulunamadı — taranmış (görsel) belge olabilir."
        )
    return text
