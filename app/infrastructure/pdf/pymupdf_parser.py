"""PDF doğrulama + metin çıkarma (docs/LLM_PIPELINE.md)."""
from __future__ import annotations

import pymupdf as fitz

from app.domain.errors import PDFValidationError


def validate_and_extract_text(pdf_bytes: bytes, max_chars: int | None = None) -> tuple[str, bool]:
    """Bozuk/şifreli/boş PDF'i sade Türkçe hata mesajıyla reddeder, geçerliyse
    (metin, kırpıldı_mı) döner.

    `max_chars` verilirse bütçe dolar dolmaz sayfa okumayı durdurur — bu PDF'i
    REDDETMEZ (kasıtlı olarak sayfa sayısı limiti yok, bkz.
    test_readable_pdf_is_not_rejected_by_unspecified_page_or_text_limits), yalnızca
    zaten LLM'e gidecek metni kırpacaksak önce tüm sayfaları gereksiz yere okumayı
    önler — küçük dosya boyutlu ama çok sayfalı bir PDF'nin CPU'yu boşuna meşgul
    etmesini engeller.

    İkinci dönüş değeri, okunmamış sayfa kaldığı için içerik gerçekten atlandığında
    True olur. Yalnızca `len(text) > max_chars` karşılaştırmasına güvenmek yanlış
    olurdu: bütçeyi dolduran sayfa aynı zamanda son sayfaysa `total` tam `max_chars`
    değerine eşit çıkabilir ve hiçbir şey atlanmamışken de bu karşılaştırma False
    döner — bkz. test_truncated_is_true_only_when_a_page_is_actually_dropped.
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
        truncated = False
        for index, page in enumerate(doc.pages()):
            chunk = page.get_text(sort=True)
            chunks.append(chunk)
            total += len(chunk)
            if max_chars is not None and total >= max_chars:
                truncated = index < doc.page_count - 1
                break
        text = "\n".join(chunks)
    finally:
        doc.close()

    if not text.strip():
        raise PDFValidationError(
            "PDF açıldı ama okunabilir metin bulunamadı — taranmış (görsel) belge olabilir."
        )
    return text, truncated
