"""candidateName kaynak-doğrulama testleri.

Gerçek bir canlı koşu bulgusundan doğdu: 7B model Türkçe aksanlı bir ismi
kopyalarken harf değiştirdi (docs/VALIDATION.md koşu #6).
"""
from app.domain.grounding import (
    ground_narrative,
    is_grounded_claim_in_source,
    is_grounded_in_source,
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


def test_evidence_grounding_tolerates_diacritics_and_one_copy_typo():
    assert is_grounded_claim_in_source(
        "8 yıldık React uzmanlık deneyimim",
        "8 yillik React uzmanlik deneyimim",
    )


def test_evidence_grounding_rejects_invented_terms_and_numbers():
    assert not is_grounded_claim_in_source("React ve Kubernetes", "React")
    assert not is_grounded_claim_in_source("React ile 10 yıl", "React ile 8 yil")


# --- Canlı koşu #9: narrative alanların blok halinde silinmesi ---------------
# 5 CV'lik gerçek koşuda üç adayın üçünde de kaynakta açıkça yazan uzaktan-çalışma
# bilgisi normalize JSON'a hiç giremedi ve kriter 3/3 yanlış 0 aldı. Sebep model
# değildi: model bilgiyi doğru çıkarıyordu, `_ground_profile` summary'yi kimlik
# alanlarıyla aynı kelime-kelime kuralına sokup tüm bloğu siliyordu.

DENIZ_CV = """DENİZ AKSOY
Trendyol — Kıdemli Frontend Geliştirici (2021–halen, tam uzaktan)
React 18, TypeScript ve Next.js ile ödeme akışını yeniden yazdım.
2021'den beri tamamen uzaktan çalışıyorum; asenkron iletişim ve yazılı
dokümantasyon konusunda deneyimliyim. 7 yıl React.
"""


def test_narrative_keeps_grounded_sentences_and_drops_the_rest():
    """Tek doğrulanamayan cümle, yanındaki gerçek bilgiyi de götürmemeli."""
    summary = (
        "Kıdemli Frontend Geliştirici. "
        "7 yıl React deneyimi ve uzaktan çalışma deneyimi sahibi. "
        "Payment flow yeniden yazımı projeleri yönetti."
    )
    result = ground_narrative(summary, DENIZ_CV)

    assert result is not None
    # Kaynağa dayanan iki cümle korunur — uzaktan bilgisi profile ulaşır.
    assert "uzaktan" in result
    assert "Kıdemli Frontend Geliştirici" in result
    # Uydurma cümle atılır: payment/flow/yönetti kaynakta yok.
    assert "Payment flow" not in result
    assert "yönetti" not in result


def test_narrative_returns_none_when_no_sentence_is_grounded():
    assert ground_narrative("Kubernetes ve Terraform uzmanıdır.", DENIZ_CV) is None
    assert ground_narrative(None, DENIZ_CV) is None
    assert ground_narrative("   ", DENIZ_CV) is None


def test_narrative_grounding_does_not_weaken_the_hallucination_guard():
    """Gramatik dolgu ayıklanıyor diye uydurma terim geçmemeli."""
    # "sahibi" dolgu -> ayıklanır, gerçek claim korunur.
    assert ground_narrative("React deneyimi sahibi.", DENIZ_CV) is not None
    # Uydurma teknoloji -> aynı kalıpta bile reddedilir.
    assert ground_narrative("Kubernetes deneyimi sahibi.", DENIZ_CV) is None
    # Yanlış süre -> reddedilir (kaynakta 7 yıl yazıyor).
    assert ground_narrative("12 yıl React deneyimi sahibi.", DENIZ_CV) is None
