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
from hashlib import sha256


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


def locate_quote(source_text: str, quote: str) -> tuple[int, int] | None:
    """Kaynakta birebir veya yalnız boşlukları değişmiş kesintisiz alıntıyı bulur."""
    direct = source_text.find(quote)
    if direct >= 0:
        return direct, direct + len(quote)

    parts = quote.strip().split()
    if not parts:
        return None
    match = re.search(r"\s+".join(re.escape(part) for part in parts), source_text)
    return None if match is None else (match.start(), match.end())


def make_evidence_id(
    document_id: int,
    criterion_id: str,
    start: int,
    end: int,
    quote: str,
) -> str:
    """Aynı kaynak span'ı için süreçler arasında kararlı, backend-owned ID üretir."""
    payload = f"{document_id}\x1f{criterion_id}\x1f{start}\x1f{end}\x1f{quote}"
    return "ev_" + sha256(payload.encode()).hexdigest()[:16]


_GENERIC_CRITERION_WORDS = {
    "aday", "ability", "candidate", "calisma", "compatibility", "deneyim",
    "deneyimi", "experience", "icin", "konusunda", "skills", "tecrube",
    "tecrubesi", "uyum", "uyumu", "work", "working", "yazimi", "yazma",
}


def _criterion_terms(texts: list[str]) -> set[str]:
    return {
        word
        for text in texts
        for word in _words(text.replace("_", " ").replace("-", " "))
        if len(word) >= 4 and word not in _GENERIC_CRITERION_WORDS
    }


def has_criterion_term(value: str, criterion_texts: list[str]) -> bool:
    """Explicit contradiction gibi dar kontroller için dinamik terim örtüşmesi."""
    return bool(set(_words(value)) & _criterion_terms(criterion_texts))


_NEGATION_WORDS = {
    "degil", "hayir", "istemem", "istemiyorum", "never", "no", "none",
    "not", "olmadan", "olmadi", "without", "yok",
}


def has_explicit_negation(value: str) -> bool:
    """Verifier'ın `contradicts` kararını açık olumsuzlukla sınırlar."""
    return bool(set(_words(value)) & _NEGATION_WORDS)


def find_criterion_passages(
    source_text: str,
    criterion_texts: list[str],
    limit: int = 3,
) -> list[str]:
    """LLM recall fallback: explicit dinamik terim geçen exact source pasajları."""
    terms = _criterion_terms(criterion_texts)
    if not terms:
        return []

    spans = [
        match.span()
        for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", source_text, flags=re.DOTALL)
    ]
    spans.extend(match.span() for match in re.finditer(r"(?m)^\s*\S.*$", source_text))
    candidates = []
    seen = set()
    for start, end in spans:
        while start < end and source_text[start].isspace():
            start += 1
        while end > start and source_text[end - 1].isspace():
            end -= 1
        quote = source_text[start:end]
        if not 3 <= len(quote) <= 320 or quote in seen:
            continue
        overlap = set(_words(quote)) & terms
        if overlap:
            seen.add(quote)
            candidates.append((len(overlap), -len(quote), start, quote))
    candidates.sort(reverse=True)
    selected: list[tuple[int, int, str]] = []
    for _overlap, _length, start, quote in candidates:
        end = start + len(quote)
        if any(start < old_end and old_start < end for old_start, old_end, _ in selected):
            continue
        selected.append((start, end, quote))
        if len(selected) == limit:
            break
    return [quote for _start, _end, quote in selected]
