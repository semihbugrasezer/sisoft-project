"""candidateName kaynak-doğrulama testleri.

Gerçek bir canlı koşu bulgusundan doğdu: 7B model Türkçe aksanlı bir ismi
kopyalarken harf değiştirdi (docs/VALIDATION.md koşu #6).
"""
from app.domain.grounding import (
    find_criterion_passages,
    has_criterion_term,
    has_explicit_negation,
    is_grounded_in_source,
    locate_quote,
    make_evidence_id,
)

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


def test_locate_quote_returns_backend_offsets():
    source = "Ada\n2021'den beri fully remote çalışmaktadır.\nReact"

    start, end = locate_quote(source, "2021'den beri fully remote çalışmaktadır.") or (-1, -1)

    assert source[start:end] == "2021'den beri fully remote çalışmaktadır."


def test_locate_quote_tolerates_only_whitespace_changes():
    source = "React ile 4 yıl\nfrontend geliştirme deneyimi"

    span = locate_quote(source, "React ile 4 yıl frontend geliştirme deneyimi")

    assert span is not None
    assert source[slice(*span)] == "React ile 4 yıl\nfrontend geliştirme deneyimi"
    assert locate_quote(source, "React ile 5 yıl frontend geliştirme deneyimi") is None
    assert locate_quote("uzaktan çalışmıyorum", "uzaktan çalışıyorum") is None


def test_evidence_id_is_stable_and_bound_to_source_span():
    first = make_evidence_id(0, "react", 10, 20, "React")

    assert first == make_evidence_id(0, "react", 10, 20, "React")
    assert first != make_evidence_id(0, "remote", 10, 20, "React")


def test_dynamic_term_fallback_preserves_qualified_exact_passage():
    source = "Python uzmanı. React deneyimim sınırlı, birkaç küçük projede kullandım."

    passages = find_criterion_passages(source, ["React tecrübesi", "React.js"])

    assert passages == ["React deneyimim sınırlı, birkaç küçük projede kullandım."]


def test_unrelated_stack_cannot_be_an_explicit_contradiction():
    assert not has_criterion_term(
        "Python ve Go ile backend sistemler geliştirdi.",
        ["Temiz kod yazımı", "Clean Code", "code review"],
    )


def test_criterion_slug_words_are_available_to_contradiction_guard():
    assert has_criterion_term(
        "Uzaktan çalışmıyorum, yalnız ofis düşünüyorum.",
        ["uzaktan_calisma_uyumu", "fully remote"],
    )


def test_explicit_negation_is_detected_without_treating_limited_as_negative():
    assert has_explicit_negation("Uzaktan çalışma deneyimim yok.")
    assert has_explicit_negation("I have no remote work experience.")
    assert not has_explicit_negation("React deneyimim sınırlı.")
