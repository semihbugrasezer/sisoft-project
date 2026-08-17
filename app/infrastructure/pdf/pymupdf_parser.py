"""PDF doğrulama + metin çıkarma (README.md §4)."""
from __future__ import annotations

import pymupdf as fitz

from app.domain.errors import PDFValidationError

def validate_and_extract_text(pdf_bytes: bytes) -> str:
    """Bozuk/şifreli/boş PDF'i sade Türkçe hata mesajıyla reddeder, geçerliyse metni döner."""
    if not pdf_bytes:
        raise PDFValidationError("Dosya boş görünüyor.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PDFValidationError("Dosya geçerli bir PDF değil.")
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFValidationError("PDF açılamadı, dosya bozuk olabilir.") from exc

    try:
        if doc.is_encrypted:
            raise PDFValidationError("PDF şifreli; lütfen şifresiz bir kopya yükleyin.")
        if doc.page_count == 0:
            raise PDFValidationError("PDF içinde sayfa bulunamadı.")

        text = "\n".join(page.get_text(sort=True) for page in doc)
    finally:
        doc.close()

    if not text.strip():
        raise PDFValidationError(
            "PDF açıldı ama okunabilir metin bulunamadı — taranmış (görsel) belge olabilir."
        )
    return text
