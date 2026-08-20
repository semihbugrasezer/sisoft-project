#!/usr/bin/env python3
"""Ödev PDF'indeki senaryoyu GERÇEK model sunucusuna karşı çalıştıran kabul testi.

Otomatik test paketi (pytest) taklit LLM kullanır; "kod sözleşmelere uyuyor mu?"
sorusunu yanıtlar. Bu script farklı bir soruyu yanıtlar: **"yapılandırılmış model
ödevin gerçek senaryosunu geçebiliyor mu?"**

Kritik nokta: script yalnızca "MultiAnalysisResponse oluştu" diye PASS vermez —
dönen adayların ortalamalarını KENDİSİ yeniden hesaplar ve top-3'ün kendi içindeki
sıralamasını doğrular. Aksi halde skorlama hatası testi de birlikte yanıltırdı.
(Top-3 SEÇİM algoritması ayrıca tests/test_scoring.py'de deterministik test edilir.)

CI'a konmaz: gerçek LLM deterministik değildir ve dakikalar sürer. Bir modelin
"desteklenen" sayılması için bu script'i geçmesi beklenir.

Kullanım:
    python scripts/validate_assignment.py           # kriterler + tekli CV (~3 dk)
    python scripts/validate_assignment.py --full    # + 5 CV batch, top-3 (~15 dk)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.container import build_container  # noqa: E402
from app.domain.models import MAX_CV_COUNT, MultiAnalysisResponse  # noqa: E402
from app.presentation.telegram.formatter import format_single_analysis  # noqa: E402

# Ödev PDF §2'deki serbest metin örneğinin BİREBİR kendisi. Kullanıcı komut
# kullanmaz — kriterleri normal sohbet içinde tanımlar.
ASSIGNMENT_CRITERIA_MESSAGE = (
    "Bana bu CV'yi React tecrübesi, temiz kod yazımı ve "
    "uzaktan çalışma uyumuna göre skorla"
)

# Yukarıdaki cümlede geçen üç kriter. Ödev etiketin kelimesi kelimesine aynı
# olmasını istemiyor (PDF'in kendi JSON örneği "Clean Code" gösteriyor), ama bu
# KABUL TESTİ üç kriterin de yakalandığını kanıtlamalı — dolayısıyla eşleşme
# ayırt edici olmalı: kelime sayısı eşit, son kelimede çekim toleransı
# (bkz. _label_matches). "React" tek başına "React tecrübesi"ni geçemez.
EXPECTED_CRITERIA = [
    "React tecrübesi",
    "temiz kod yazımı",
    "uzaktan çalışma uyumu",
]

ACCEPTANCE_CHAT_ID = -999_001  # gerçek sohbetlerle karışmasın


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def _label_matches(expected: str, actual: str) -> bool:
    """Kelime bazlı sıkı eşleşme, yalnız son kelimede Türkçe çekim toleransı.

    Neden düz `startswith` değil: "React" tek başına "React tecrübesi"nin öneki
    olduğu için eksik bir etiketi PASS ettirirdi. Kelime sayısı eşitliği bunu
    engeller. Neden tam eşitlik de değil: etiket kullanıcının cümlesindeki çekimi
    devralabilir ("uyumu" / "uyumuna") ve bu kabul edilebilir bir farktır.
    """
    expected_words = _norm(expected).split()
    actual_words = _norm(actual).split()
    if len(expected_words) != len(actual_words):
        return False
    *expected_head, expected_last = expected_words
    *actual_head, actual_last = actual_words
    if expected_head != actual_head:
        return False
    return actual_last.startswith(expected_last) or expected_last.startswith(actual_last)


def _matches(expected: str, actual_labels: list[str]) -> bool:
    return any(_label_matches(expected, actual) for actual in actual_labels)


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {label}{suffix}", flush=True)
        if not ok:
            self.failures.append(label)
        return ok


async def run(full: bool) -> int:
    config = load_config()
    container = build_container(config)
    report = Report()

    print(f"\nBackend : {config.llm_backend}")
    print(f"Model   : {config.llm_model}")
    print(f"Adres   : {config.llm_base_url}")
    print(f"Mod     : {'--full (5 CV batch)' if full else 'varsayılan (tekli CV)'}\n")

    try:
        # --- 1) Serbest metinden dinamik kriter (PDF §2) ---------------------
        print("1) Serbest metinden kriter çıkarımı")
        t0 = time.monotonic()
        criteria = await container.criteria_service.define_if_requested(
            ACCEPTANCE_CHAT_ID, ASSIGNMENT_CRITERIA_MESSAGE
        )
        elapsed = time.monotonic() - t0
        labels = [c.label for c in criteria] if criteria else []

        report.check(criteria is not None, "Mesaj kriter tanımı olarak sınıflandırıldı",
                     f"{elapsed:.1f}s")
        found = [e for e in EXPECTED_CRITERIA if _matches(e, labels)]
        report.check(
            len(found) == len(EXPECTED_CRITERIA),
            f"Kriter eksiksizliği: {len(found)}/{len(EXPECTED_CRITERIA)}",
            f"çıkarılan: {labels}",
        )
        if not criteria:
            print("\nKriter çıkarılamadı — sonraki adımlar atlanıyor.")
            return 1

        # --- 2) PDF doğrulama + LLM Extraction + değerlendirme (PDF §2-3) ----
        cv_paths = sorted(Path("mock_cvs").glob("*.pdf"))
        if not cv_paths:
            print("\nmock_cvs/ boş — önce scripts/generate_mock_cvs.py çalıştırın.")
            return 1

        print("\n2) Tekli CV: doğrulama → LLM Extraction → değerlendirme")
        t0 = time.monotonic()
        profile, evaluation, _ = await container.cv_service.analyze(
            cv_paths[0].read_bytes(), criteria
        )
        elapsed = time.monotonic() - t0
        report.check(True, "Tekli CV analizi tamamlandı", f"{elapsed:.1f}s")
        report.check(
            profile.candidateName is not None,
            "Ortak JSON şemasına çıkarım (candidateName)",
            f"{profile.candidateName!r}, {len(profile.skills)} yetenek",
        )
        scored = [s.criterionLabel for s in evaluation.scores]
        report.check(
            len(evaluation.scores) == len(criteria),
            f"Her kritere puan verildi: {len(evaluation.scores)}/{len(criteria)}",
            f"{scored}",
        )
        # PDF §2 raporda güçlü yönler, zayıf yönler VE gelişim tavsiyeleri istiyor.
        # Hangi alanın boş kaldığını göstermek önemli: bu bir kod hatası değil,
        # model kalitesi ölçümüdür — teşhis edilebilir olmalı.
        sections = {
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
            "recommendations": evaluation.recommendations,
        }
        empty = [name for name, value in sections.items() if not value]
        report.check(
            not empty,
            "Nitel rapor alanları dolu (güçlü/zayıf/tavsiye)",
            "boş: " + ", ".join(empty) if empty else
            ", ".join(f"{k}={len(v)}" for k, v in sections.items()),
        )

        # Markdown şablonunun PDF'in istediği başlıkları ürettiğini doğrula.
        # Ek LLM çağrısı gerektirmez — eldeki sonucu formatlar.
        rendered = format_single_analysis(profile, evaluation)
        missing = [h for h in ("Güçlü Yönler", "Zayıf Yönler", "Gelişim Tavsiyeleri")
                   if h not in rendered]
        report.check(
            not missing,
            "Markdown rapor başlıkları üretildi",
            "eksik: " + ", ".join(missing) if missing else f"{len(rendered)} karakter",
        )

        # --- 3) Çoklu CV → top-3 JSON (PDF §4) -------------------------------
        if full:
            # Ödevin çoklu senaryosu 5 CV üzerinden tanımlı; fixture eksikse
            # acceptance'ın önemli bir bölümü sessizce daha zayıf bir senaryoyu
            # test etmiş olurdu.
            if len(cv_paths) < MAX_CV_COUNT:
                report.check(
                    False,
                    f"{MAX_CV_COUNT} mock CV mevcut",
                    f"bulunan: {len(cv_paths)} — scripts/generate_mock_cvs.py çalıştırın",
                )
                return 1
            files = [(p.name, p.read_bytes()) for p in cv_paths[:MAX_CV_COUNT]]
            report.check(len(files) == MAX_CV_COUNT, f"Batch CV sayısı = {MAX_CV_COUNT}")
            print(f"\n3) Çoklu CV batch ({len(files)} CV) — birkaç dakika sürebilir")
            t0 = time.monotonic()
            response, _ = await container.batch_service.analyze_batch(files, criteria)
            elapsed = time.monotonic() - t0
            report.check(True, "Batch analizi tamamlandı", f"{elapsed:.1f}s")

            _verify_response(response, files, criteria, report)

        print()
        if report.failures:
            print(f"SONUÇ: FAIL — {len(report.failures)} kontrol başarısız")
            for name in report.failures:
                print(f"  - {name}")
            return 1
        print("SONUÇ: PASS — ödev senaryosunun tüm kontrolleri geçti")
        return 0
    finally:
        await container.repo.clear_criteria(ACCEPTANCE_CHAT_ID)
        await container.repo.close()
        await container.llm.aclose()


def _verify_response(response: MultiAnalysisResponse, files, criteria, report: Report) -> None:
    """Dönen top-3'ü bağımsız doğrular: her adayın ortalaması yeniden hesaplanır
    ve üçlünün kendi içindeki sıralaması kontrol edilir.

    Kapsam sınırı: script yalnızca DÖNEN üç adayı görür, elenen 4. ve 5. adayın
    ortalamasını bilmez — dolayısıyla "bu üçü gerçekten en yükseği mi?" sorusunu
    buradan kanıtlayamaz. Top-3 SEÇİM algoritması (eşitlik durumu dahil)
    tests/test_scoring.py'de deterministik olarak test edilir."""
    print("\n4) Çıktı sözleşmesi (bağımsız doğrulama)")

    report.check(response.status == "success", "status = success")
    report.check(
        response.processedCVCount == len(files),
        f"processedCVCount = {len(files)}",
        str(response.processedCVCount),
    )
    report.check(
        len(response.topCandidates) == 3,
        "topCandidates sayısı = 3",
        str(len(response.topCandidates)),
    )
    report.check(
        [c.rank for c in response.topCandidates] == [1, 2, 3],
        "rank değerleri = [1, 2, 3]",
        str([c.rank for c in response.topCandidates]),
    )

    labels = [c.label for c in criteria]
    report.check(
        set(response.userDefinedCriteria) == set(labels),
        "userDefinedCriteria kullanıcı kriterleriyle eşleşiyor",
    )

    all_scored = all(
        set(c.dynamicScores) == set(labels) for c in response.topCandidates
    )
    report.check(all_scored, "Her adayda tüm kriterlerin skoru var")

    # Ortalamayı BAĞIMSIZ yeniden hesapla — scoring.py'ye güvenme; aksi halde
    # oradaki bir hata bu testi de birlikte yanıltırdı.
    arithmetic_ok = True
    for candidate in response.topCandidates:
        values = list(candidate.dynamicScores.values())
        expected = round(sum(values) / len(values), 2)
        if abs(expected - candidate.averageScore) > 0.01:
            arithmetic_ok = False
            print(f"      {candidate.pdfFileName}: beklenen {expected}, "
                  f"gelen {candidate.averageScore}")
    report.check(arithmetic_ok, "Dönen adayların ortalamaları bağımsız yeniden hesaplandı")

    averages = [c.averageScore for c in response.topCandidates]
    report.check(
        averages == sorted(averages, reverse=True),
        "Dönen top-3 kendi içinde azalan sırada",
        str(averages),
    )

    # Şemayı tekrar doğrula (extra="forbid" dahil).
    try:
        MultiAnalysisResponse.model_validate_json(response.model_dump_json())
        report.check(True, "Nihai JSON şemayı doğruluyor")
    except Exception as exc:  # pragma: no cover - kabul testi yolu
        report.check(False, "Nihai JSON şemayı doğruluyor", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full", action="store_true",
        help=f"{MAX_CV_COUNT} CV'lik batch ve top-3 JSON doğrulamasını da çalıştır",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.full))


if __name__ == "__main__":
    raise SystemExit(main())
