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


def _normalize(text: str) -> str:
    # NFKC: farklı Unicode gösterimlerini (örn. birleşik/ayrık aksan) tek biçime indirger.
    # casefold: Unicode-farkındalıklı küçük harfe çevirme (str.lower()'dan güçlü).
    return unicodedata.normalize("NFKC", text).casefold()


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
