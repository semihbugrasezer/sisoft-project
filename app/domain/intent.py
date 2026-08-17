"""Kriter tanımlama niyetini ucuz bir anahtar-kelime heuristiğiyle tespit eder.

ponytail: Her sohbet mesajını ayrı bir LLM intent-classifier çağrısına sokmak yerine
(bu modelde ~60-90sn/çağrı — her chat mesajını bu kadar geciktirmek demo'yu bozar)
hızlı bir substring eşleştirme kullanılır. Yanlış negatif olursa kullanıcı /criteria
ile açıkça tetikleyebilir (RULES.md §4). Yükseltme yolu: yanlış pozitif/negatif oranı
sorun olursa CriteriaExtractor'ın kendisi "kriter bulunamadı" da dönebilecek şekilde
genişletilip tek çağrıda hem sınıflandırma hem extraction yapılabilir.
"""
from __future__ import annotations

_CRITERIA_KEYWORDS = (
    "kriter",
    "skorla",
    "puanla",
    "değerlendir",
    "degerlendir",
    "puanlama",
    "göre analiz",
    "gore analiz",
)


def looks_like_criteria_definition(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _CRITERIA_KEYWORDS)
