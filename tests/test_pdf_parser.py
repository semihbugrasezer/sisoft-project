from pathlib import Path

import pymupdf
import pytest

from app.domain.errors import PDFValidationError
from app.infrastructure.pdf.pymupdf_parser import validate_and_extract_text

CV_TEXT = (
    "Ada Örnek\nYazılım Geliştirici\nada@example.com\n"
    "React, Python, PostgreSQL ve Git yetenekleri.\n"
    "TechCo şirketinde 2020-2025 arasında uzaktan çalıştı.\n"
    "Bilgisayar Mühendisliği, ODTÜ.\nTürkçe ve İngilizce konuşur."
)


def _layout_pdf(layout):
    doc = pymupdf.open()
    if layout == "single":
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 790), CV_TEXT, fontsize=11)
    elif layout == "columns":
        page = doc.new_page()
        left, right = CV_TEXT.split("TechCo")
        page.insert_textbox(pymupdf.Rect(40, 50, 285, 790), left, fontsize=10)
        page.insert_textbox(pymupdf.Rect(310, 50, 555, 790), "TechCo" + right, fontsize=10)
    elif layout == "multipage":
        first, second = CV_TEXT.split("React")
        doc.new_page().insert_text((50, 70), first, fontsize=11)
        doc.new_page().insert_textbox(
            pymupdf.Rect(50, 50, 545, 790), "React" + second, fontsize=11
        )
    else:
        page = doc.new_page()
        for row, (label, value) in enumerate(
            [
                ("Aday", "Ada Örnek — Yazılım Geliştirici"),
                ("İletişim", "ada@example.com"),
                ("Yetenekler", "React, Python, PostgreSQL ve Git"),
                ("Deneyim", "TechCo, 2020-2025, uzaktan çalışma"),
                ("Eğitim", "Bilgisayar Mühendisliği, ODTÜ"),
                ("Diller", "Türkçe ve İngilizce"),
            ]
        ):
            y = 70 + row * 35
            page.draw_rect(pymupdf.Rect(45, y - 18, 550, y + 8))
            page.insert_text((55, y), label, fontsize=10)
            page.insert_text((170, y), value, fontsize=10)
    payload = doc.tobytes()
    doc.close()
    return payload


@pytest.mark.parametrize("pdf_path", sorted(Path("mock_cvs").glob("*.pdf")))
def test_mock_cvs_are_readable(pdf_path):
    assert len(validate_and_extract_text(pdf_path.read_bytes())) >= 100


@pytest.mark.parametrize("layout", ["single", "columns", "multipage", "table"])
def test_different_pdf_layouts_are_readable(layout):
    text = validate_and_extract_text(_layout_pdf(layout))
    assert "Ada" in text
    assert "React" in text


def test_encrypted_pdf_is_rejected():
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 70), CV_TEXT)
    payload = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="secret",
    )
    doc.close()

    with pytest.raises(PDFValidationError, match="PDF şifreli"):
        validate_and_extract_text(payload)


def test_readable_pdf_is_not_rejected_by_unspecified_page_or_text_limits():
    doc = pymupdf.open()
    for _ in range(31):
        doc.new_page().insert_text((50, 70), "A")
    payload = doc.tobytes()
    doc.close()

    assert validate_and_extract_text(payload).strip()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "Dosya boş"),
        (b"not a pdf", "geçerli bir PDF değil"),
        (b"%PDF-broken", "PDF açılamadı"),
    ],
)
def test_invalid_pdf_is_rejected(payload, message):
    with pytest.raises(PDFValidationError, match=message):
        validate_and_extract_text(payload)
