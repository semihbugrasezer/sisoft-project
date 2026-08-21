"""candidateName kaynak-doğrulama testleri.

Gerçek bir canlı koşu bulgusundan doğdu: 7B model Türkçe aksanlı bir ismi
kopyalarken harf değiştirdi (docs/VALIDATION.md koşu #6).
"""
from app.domain.grounding import is_grounded_claim_in_source, is_grounded_in_source

CV = """Semih Buğra Sezer
Yazılım Geliştirici
React, Python, PostgreSQL
"""


def test_exact_name_is_grounded():
    assert is_grounded_in_source("Semih Buğra Sezer", CV)


def test_model_corrupted_turkish_name_is_rejected():
    # Canlı koşuda gözlenen gerçek bozulma: harf yer değiştirmesi.
    assert not is_grounded_in_source("Semhi Bügüra Sezer", CV)


def test_case_and_unicode_form_differences_are_tolerated():
    assert is_grounded_in_source("SEMİH BUĞRA SEZER".replace("İ", "I"), CV.upper())
    assert is_grounded_in_source("semih buğra sezer", CV)


def test_reordered_or_line_split_name_is_grounded():
    # "Sezer, Semih" gibi farklı sıralama veya satır sonuyla bölünme kabul edilir;
    # kelime bazlı kontrol bunu tolere ederken uydurmayı yine yakalar.
    assert is_grounded_in_source("Sezer Semih", CV)


def test_hallucinated_name_is_rejected():
    assert not is_grounded_in_source("John Smith", CV)


def test_partially_hallucinated_name_is_rejected():
    # Bir kelimesi doğru, diğeri uydurma — kabul edilmemeli.
    assert not is_grounded_in_source("Semih Nonexistent", CV)


def test_empty_or_missing_name_is_not_grounded():
    assert not is_grounded_in_source(None, CV)
    assert not is_grounded_in_source("", CV)
    assert not is_grounded_in_source("   ", CV)


def test_evidence_grounding_tolerates_diacritics_and_one_copy_typo():
    assert is_grounded_claim_in_source(
        "8 yıldık React uzmanlık deneyimim",
        "8 yillik React uzmanlik deneyimim",
    )


def test_evidence_grounding_rejects_invented_terms_and_numbers():
    assert not is_grounded_claim_in_source("React ve Kubernetes", "React")
    assert not is_grounded_claim_in_source("React ile 10 yıl", "React ile 8 yil")
