"""Kaynak-doğrulama (grounding): LLM'in ürettiği bir alanın kaynak belgede
gerçekten geçip geçmediğini deterministik olarak kontrol eder.

Neden gerekli: Pydantic `candidateName: str | None` **tipini** doğrular, değerin
**doğru** olduğunu değil. Canlı testte 7B model Türkçe aksanlı bir ismi kopyalarken
harf değiştirdi ("Buğra" → "Bügüra", bkz. docs/VALIDATION.md koşu #6). Prompt zaten
"birebir aktar" diyor; prompt'a güvenmek yerine çıktıyı kaynağa karşı doğruluyoruz —
skor tarafında "kanıtsız yüksek puan" validator'ı ile aynı mantık.

Kelime bazlı kontrol (tam metin substring'i yerine) bilinçli: CV'lerde ad satır
sonuyla bölünebilir, farklı sırada ("Sezer, Semih") veya farklı boşluklarla yazılmış
olabilir. Kelime bazlı kontrol bunları tolere ederken uydurulmuş/bozulmuş bir kelimeyi
("bügüra") yine de yakalar.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def _normalize(text: str) -> str:
    # LLM bazen ASCII kaynak alıntısını Türkçe aksanlarla yeniden yazar. Aksanı
    # ayırıp kaldırmak içerik terimini korurken bu yüzey farkını tolere eder.
    decomposed = unicodedata.normalize("NFKD", text).casefold().replace("ı", "i")
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _normalize(text), flags=re.UNICODE)


def is_grounded_in_source(value: str | None, source_text: str) -> bool:
    """`value` içindeki her kelime `source_text` içinde de geçiyorsa True.

    Boş/None değer "grounded değil" sayılmaz — çağıran zaten None'ı ayrı ele alır;
    burada False dönmek, olmayan bir alanı hata gibi göstermek olurdu.
    """
    if not value or not value.strip():
        return False
    source_words = set(_words(source_text))
    if not source_words:
        return False
    return all(word in source_words for word in _words(value))


# Somut iddia sayılmayan gramatik kabuk. Cümle bazlı doğrulama (ground_narrative)
# devreye girdikten SONRA bu liste yük taşımaya başladı: canlı koşuda
# "7 yıl React deneyimi ve uzaktan çalışma deneyimi sahibi." cümlesi yalnız
# "sahibi" kelimesi yüzünden düşüyor, kaynakta açıkça yazan uzaktan bilgisi
# normalize JSON'a giremiyordu.
#
# Liste bilinçli olarak DAR tutulur: yalnız anlam taşımayan sarmalayıcılar.
# "tamamen", "uzaktan", "hibrit" gibi anlamı değiştiren nitelemeler ASLA
# eklenmemeli — kaynak "kısmen uzaktan" derken modelin "tamamen uzaktan" demesi
# gerçek bir sapmadır ve yakalanmaya devam etmelidir.
_EVIDENCE_STOPWORDS = {_normalize(word) for word in {
    "aday", "alanında", "bir", "bu", "candidate", "deneyim", "deneyimi",
    "deneyimlidir", "experience", "ile", "kanıt", "tecrübe", "the", "ve", "yıl",
    # edat / bağlaç
    "ancak", "ayrıca", "beri", "boyunca", "daha", "gibi", "göre", "için", "ise",
    "kadar", "konusunda", "olarak", "önce", "sonra", "üzere", "veya", "yana",
    # yüklem / iyelik kalıpları
    "bulunmaktadır", "sahibi", "sahip", "sahiptir", "vardır",
    # aday kelimesinin çekimleri
    "adaya", "adayı", "adayın",
    # süre/deneyim çekimleri
    "deneyime", "deneyimine", "deneyimli", "tecrübesi", "tecrübeye",
    "yıldır", "yıllık",
    # `_words` kesme işaretinden böler: "2021'den" -> {"2021", "den"}
    "dan", "den", "tan", "ten",
}}


def _evidence_words(value: str) -> set[str]:
    return {
        word for word in _words(value)
        if (len(word) >= 3 or word.isdigit()) and word not in _EVIDENCE_STOPWORDS
    }


def _term_matches_source(term: str, source_term: str) -> bool:
    if term == source_term:
        return True
    if term.isdigit() or source_term.isdigit() or min(len(term), len(source_term)) < 5:
        return False
    return term[:5] == source_term[:5] or SequenceMatcher(None, term, source_term).ratio() >= 0.82


def has_grounded_term_in_source(value: str, source_text: str) -> bool:
    """Doğal dil evidence cümlesinde kaynaktan en az bir somut terim arar.

    `candidateName` birebir aktarılmalıdır ve `is_grounded_in_source` ile tüm
    kelimeleri doğrulanır. Evidence ise bir profil değerini doğal dille
    açıklayabilir; burada bağlaç/açıklama kelimeleri değil, React/PostgreSQL gibi
    en az bir içerik teriminin profile dayanması zorunludur.
    """
    evidence_words = _evidence_words(value)
    source_words = set(_words(source_text))
    return bool(evidence_words & source_words)


def is_grounded_claim_in_source(value: str, source_text: str) -> bool:
    """Evidence içindeki tüm somut terimler kaynakta bulunmalıdır."""
    evidence_words = _evidence_words(value)
    source_words = set(_words(source_text))
    return bool(evidence_words) and all(
        any(_term_matches_source(word, source_word) for source_word in source_words)
        for word in evidence_words
    )


# Anlatı alanları (summary, workExperiences.description) tek blok olarak
# `is_grounded_in_source` ile doğrulanınca pratikte HER ZAMAN siliniyordu: o kural
# değerdeki her kelimeyi kaynakta arıyor ve doğal dilde "çeşitli", "sahibim" gibi
# tek bir dolgu kelimesi tüm bloğu çöpe atıyor. Canlı 5 CV koşusunda üç adayın
# üçünde de kaynakta açıkça yazan "tam uzaktan" bilgisi bu yüzden normalize JSON'a
# hiç girmedi ve "uzaktan çalışma uyumu" kriteri 3/3 yanlış 0 aldı.
#
# Çözüm kuralı gevşetmek değil, doğru granülariteye uygulamak: blok yerine cümle.
# Kaynağa dayanan cümleler korunur, dayanmayan cümle atılır.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def ground_narrative(value: str | None, source_text: str) -> str | None:
    """Anlatı alanını cümle bazında doğrular; doğrulanamayan cümleyi atar.

    Kimlik alanları (ad, e-posta, şirket, tarih) `is_grounded_in_source` ile
    doğrulanmaya devam eder — onların birebir kopyalanması beklenir. Burada
    cümle başına `is_grounded_claim_in_source` kullanılır: cümledeki tüm somut
    terimler kaynağa dayanmalı, ama gramatik kabuk iddia sayılmaz. Yani uydurma
    bir terim içeren cümle yine atılır, sadece artık yanındaki doğru cümleleri
    beraberinde götürmez.
    """
    if not value or not value.strip():
        return None
    grounded = [
        sentence.strip()
        for sentence in _SENTENCE_BOUNDARY.split(value)
        if sentence.strip() and is_grounded_claim_in_source(sentence, source_text)
    ]
    return " ".join(grounded) or None
