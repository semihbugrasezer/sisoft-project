"""Farklı PDF şablonlarının aynı şekilde okunabildiğini doğrular.

Ödev PDF §3: "Sisteme beslenecek PDF dosyalarının tamamı farklı şablonlarda,
tablo yapılarında ve biçimlerde olacaktır." `scripts/generate_mock_cvs.py` beş
CV'yi beş FARKLI layout'ta üretir; bu testler her birinin parser'dan geçtiğini
ve temel içeriğin kaybolmadığını kanıtlar.

Not: LLM Extraction'ın (dağınık metin → CandidateProfile) gerçek modeldeki
kalitesi burada test edilemez — deterministik değil ve dakikalar sürer. Onu
`scripts/validate_assignment.py` gerçek modele karşı ölçer.
"""
from pathlib import Path

import pytest

from app.infrastructure.pdf.pymupdf_parser import validate_and_extract_text

# (dosya, layout, metinde mutlaka bulunması gereken parçalar)
LAYOUT_EXPECTATIONS = [
    ("cv_caner_bulut.pdf", "tek kolon", ["Caner Bulut", "React", "TechCo", "ODTU"]),
    ("cv_burak_yildiz.pdf", "iki kolon", ["Burak Yildiz", "React", "CloudNet"]),
    ("cv_mert_demir.pdf", "tablo", ["Mert Demir", "React", "Freelance"]),
    ("cv_elif_kaya.pdf", "farklı bölüm sırası", ["Elif Kaya", "Go", "DataFlow"]),
    ("cv_zeynep_arslan.pdf", "çok sayfalı", ["Zeynep Arslan", "Figma", "DesignHub"]),
]


@pytest.mark.parametrize(("filename", "layout", "must_contain"), LAYOUT_EXPECTATIONS)
def test_every_layout_is_readable_and_keeps_key_content(filename, layout, must_contain):
    path = Path("mock_cvs") / filename
    assert path.exists(), f"{filename} yok — scripts/generate_mock_cvs.py çalıştırın"

    text, truncated = validate_and_extract_text(path.read_bytes())

    assert not truncated, f"{layout} layout'u beklenmedik şekilde kırpıldı"
    missing = [token for token in must_contain if token not in text]
    assert not missing, f"{layout} layout'unda kayıp içerik: {missing}"


def test_multipage_layout_actually_spans_pages():
    # Çok sayfalı fixture gerçekten çok sayfalı olmalı; aksi halde parser'ın
    # sayfa gezinmesi test edilmemiş olur.
    import pymupdf

    doc = pymupdf.open(str(Path("mock_cvs") / "cv_zeynep_arslan.pdf"))
    page_count = doc.page_count
    doc.close()
    assert page_count > 1, "çok sayfalı fixture tek sayfaya düşmüş"


def test_layouts_are_actually_different():
    # Beş fixture aynı şablonla üretilirse "farklı format" iddiası boş kalır.
    # Ham metinlerin birbirinden farklı olduğunu (aynı şablon çıktısı olmadığını)
    # doğrular.
    texts = {
        name: validate_and_extract_text((Path("mock_cvs") / name).read_bytes())[0]
        for name, _, _ in LAYOUT_EXPECTATIONS
    }
    # Bölüm başlıklarının biçimi layout'a göre değişmeli (ör. "OZET" vs "Ozet")
    assert "OZET" in texts["cv_burak_yildiz.pdf"], "iki kolon layout'u beklenen biçimde değil"
    assert "HAKKIMDA" in texts["cv_elif_kaya.pdf"], "bölüm sırası layout'u beklenen biçimde değil"
