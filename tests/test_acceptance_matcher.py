"""`scripts/validate_assignment.py` içindeki kriter eşleştiricisinin testleri.

Bu helper kabul testinin doğruluğunu belirler: fazla toleranslı olursa eksik
kriter çıkarımı sessizce PASS eder. Bir kez gerçekten öyle oldu — düz
`startswith` karşılaştırması "React" etiketini "React tecrübesi" beklentisi
için kabul ediyordu. Bu testler o gerilemeyi kalıcı olarak engeller.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validate_assignment import _label_matches  # noqa: E402


@pytest.mark.parametrize(
    ("expected", "actual", "should_match"),
    [
        # Birebir ve büyük/küçük harf farkı
        ("React tecrübesi", "React tecrübesi", True),
        ("React tecrübesi", "react TECRÜBESİ", True),
        # Türkçe çekim toleransı: etiket kullanıcının cümlesindeki hâli devralır
        ("uzaktan çalışma uyumu", "uzaktan çalışma uyumuna", True),
        ("temiz kod yazımı", "temiz kod yazımını", True),
        # GERİLEME KORUMASI: eksik etiket kabul edilmemeli
        ("React tecrübesi", "React", False),
        ("temiz kod yazımı", "temiz kod", False),
        # Parafraz kabul edilmemeli (birebir-etiket sözleşmesi)
        ("React tecrübesi", "React deneyimi", False),
        # Tamamen farklı kriter
        ("React tecrübesi", "uzaktan çalışma uyumu", False),
        # Fazladan kelime
        ("React tecrübesi", "ileri React tecrübesi", False),
    ],
)
def test_label_matching(expected, actual, should_match):
    assert _label_matches(expected, actual) is should_match
