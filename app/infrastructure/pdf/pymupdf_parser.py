"""PDF doğrulama + metin çıkarma (README.md → PDF Doğrulama ve Ortak Şemaya Dönüştürme)."""
from __future__ import annotations

import pymupdf as fitz

from app.domain.errors import PDFValidationError


def validate_and_extract_text(pdf_bytes: bytes, max_chars: int | None = None) -> str:
    """Bozuk/şifreli/boş PDF'i sade Türkçe hata mesajıyla reddeder, geçerliyse metni döner.

    `max_chars` verilirse bütçe dolar dolmaz sayfa okumayı durdurur — bu PDF'i
    REDDETMEZ (kasıtlı olarak sayfa sayısı limiti yok, bkz.
    test_readable_pdf_is_not_rejected_by_unspecified_page_or_text_limits), yalnızca
    zaten LLM'e gidecek metni kırpacaksak önce tüm sayfaları gereksiz yere okumayı
    önler — küçük dosya boyutlu ama çok sayfalı bir PDF'nin CPU'yu boşuna meşgul
    etmesini engeller.
    """
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

        chunks: list[str] = []
        total = 0
        for page in doc:
            chunk = page.get_text(sort=True)
            chunks.append(chunk)
            total += len(chunk)
            if max_chars is not None and total >= max_chars:
                break
        text = "\n".join(chunks)
    finally:
        doc.close()

    if not text.strip():
        raise PDFValidationError(
            "PDF açıldı ama okunabilir metin bulunamadı — taranmış (görsel) belge olabilir."
        )
    return text
