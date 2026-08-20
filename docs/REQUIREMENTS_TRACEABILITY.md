# Gereksinim İzlenebilirlik Matrisi

Ödev PDF'indeki her gereksinimi, onu karşılayan koda ve o kodu doğrulayan
teste bağlar. Amaç, "yapıldı" iddiasını tek tek doğrulanabilir hale getirmek.

Sütunların anlamı:

- **Uygulama** — gereksinimi karşılayan asıl kod.
- **Doğrulama** — otomatik test (mock LLM ile) ve/veya gerçek model
  sunucusuna karşı canlı koşu ([VALIDATION.md](./VALIDATION.md)).

## Fonksiyonel Gereksinimler (PDF §1-4)

| ID | Gereksinim | Uygulama | Doğrulama |
|---|---|---|---|
| FR-01 | Günlük sohbet, yerel dil modeliyle mantıklı/akıcı yanıt | `app/application/chat_service.py` | `tests/test_chat_service.py`; canlı koşu #4, #6 |
| FR-02 | Sohbet geçmişi backend'de güvenli yönetilir, bağlam kaybolmaz | `chat_service.py` (sıcak pencere `CHAT_HISTORY_LIMIT`=40 + rolling summary), `sqlite_repo.py` | `tests/test_chat_service.py`, `tests/test_sqlite_repo.py`; canlı koşu #4 |
| FR-03 | Sabit kriter yok; kullanıcı kriterleri serbest metinle tanımlar | `app/application/criteria_service.py` (LLM intent + extraction, komut zorunlu değil) | `tests/test_criteria_service.py` (özellikle `test_free_text_without_keyword_can_define_criteria`) |
| FR-04 | Kriter etiketleri kullanıcının ifadesini yansıtır | `criteria_service.py` → `_grounded_criteria`, `_all_labels_exact` | `tests/test_criteria_service.py::test_paraphrased_but_grounded_label_triggers_verbatim_retry` |
| FR-05 | Tekli CV → dinamik kriterlere göre nitel analiz raporu | `app/application/cv_analysis_service.py::analyze` | `tests/test_cv_analysis_service.py`; canlı koşu #6 |
| FR-06 | Raporda güçlü yönler, zayıf yönler, gelişim tavsiyeleri | `app/domain/models.py::EvaluationResult` (`strengths`/`weaknesses`/`recommendations`) | `tests/test_models.py`, `tests/test_formatter.py` |
| FR-07 | Telegram'da okunaklı Markdown şablonu | `app/presentation/telegram/formatter.py::format_single_analysis` | `tests/test_formatter.py`, `tests/test_handlers.py` |
| FR-08 | Bozuk/şifreli/okunamaz/geçersiz PDF backend'de yakalanır | `app/infrastructure/pdf/pymupdf_parser.py` (6 senaryo: boş, imza, açılamayan, şifreli, sayfasız, metinsiz) | `tests/test_pdf_parser.py`; `scripts/generate_invalid_cvs.py` ile canlı Telegram testi |
| FR-09 | Hata tespitinde süreç kesilir, kullanıcıya net mesaj döner | `app/domain/errors.py` (`AppError` hiyerarşisi), `handlers.py` | `tests/test_handlers.py`, `tests/test_batch_analysis.py` |
| FR-10 | Ham PDF metni doğrudan analiz edilmez; önce ortak JSON şeması | `models.py::CandidateProfile` + `prompts.py::CV_EXTRACTOR_SYSTEM` | `tests/test_cv_analysis_service.py::test_batch_uses_two_llm_calls_and_scores_only_normalized_profiles` |
| FR-11 | Puanlama/analiz/filtreleme **yalnızca** ortak JSON üzerinden | `cv_analysis_service.py` — evaluator prompt'u yalnız `profile.model_dump_json()` alır, ham metin girmez | Aynı test: ham kaynak metnin ikinci prompt'ta bulunmadığını doğrular |
| FR-12 | En fazla 5 CV toplu gönderim | `models.py::MAX_CV_COUNT = 5`, `batch_analysis_service.py` | `tests/test_batch_analysis.py::test_more_than_five_cvs_is_rejected_before_processing` |
| FR-13 | Dosyalar asenkron/paralel işlenir | `batch_analysis_service.py::_validate_all_or_abort` (`asyncio.gather`), `cv_analysis_service.py::extract_text` (`asyncio.to_thread`) | `tests/test_batch_analysis.py`; bkz. [CONCURRENCY.md](./CONCURRENCY.md) |
| FR-14 | Her CV'ye kriter bazlı puan, aritmetik ortalama | `app/domain/scoring.py::compute_average` (backend'de deterministik, LLM'e yaptırılmaz) | `tests/test_scoring.py` |
| FR-15 | En yüksek ortalamalı ilk 3 aday | `scoring.py::rank_top_n` | `tests/test_scoring.py` (eşitlik durumu dahil) |
| FR-16 | Çıktı, PDF §4'teki JSON şemasıyla birebir | `models.py::MultiAnalysisResponse` / `TopCandidate` (`extra="forbid"`) | `tests/test_models.py`, `tests/test_batch_analysis.py`; canlı koşu #7 |

## Teknik Beklentiler (PDF §Teknik Beklentiler)

| ID | Gereksinim | Uygulama | Doğrulama |
|---|---|---|---|
| NFR-01 | Nesne yönelimli, katmanlı mimari | `app/{domain,application,infrastructure,presentation}` | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| NFR-02 | Python (kabul edilen dillerden biri) | Python 3.13 / 3.14 | CI matrisi (`.github/workflows/ci.yml`) |
| NFR-03 | Telegram Long Polling veya Webhook | `main.py` → `application.run_polling()` | `tests/test_router.py` |
| NFR-04 | Kilitlenmeyen asenkron mesajlaşma | `router.py` → `concurrent_updates(8)`, `handlers.py` → chat_id bazlı `asyncio.Lock` | [CONCURRENCY.md](./CONCURRENCY.md); canlı koşu: batch sırasında bot yanıt vermeye devam etti |
| NFR-05 | Ollama entegrasyonu | `infrastructure/llm/ollama_client.py` (`/api/chat`) | `tests/test_ollama_client.py`; canlı koşu #1-#7 |
| NFR-06 | vLLM / LM Studio entegrasyonu | `infrastructure/llm/openai_compatible_client.py` (`/v1/chat/completions`) | `tests/test_openai_compatible_client.py`; LM Studio canlı doğrulandı, vLLM protokol uyumlu (donanım kısıtı, bkz. VALIDATION.md) |

## Değerlendirme Kriterleri (PDF §Değerlendirme Kriterleri)

| ID | Kriter | Nerede görülür |
|---|---|---|
| EVAL-01 | Dinamik prompt başarısı — sohbetten gelen kriterleri prompt'a gömme, tekli/çoklu modları kararlı çalıştırma | `infrastructure/llm/prompts.py`, `criteria_service.py`; [LLM_PIPELINE.md](./LLM_PIPELINE.md) |
| EVAL-02 | PDF doğrulama ve LLM Extraction kalitesi | `pymupdf_parser.py`, `CandidateProfile`; Pydantic validator'ları (`CriterionScore` kanıtsız yüksek puanı reddeder) |
| EVAL-03 | Asenkron süreç ve bağlam yönetimi | [CONCURRENCY.md](./CONCURRENCY.md); rolling summary (`chat_service.py`) |
| EVAL-04 | AI destekli geliştirmede üretilen mimariye/koda hâkimiyet | [AI_ASSISTED_DEVELOPMENT.md](./AI_ASSISTED_DEVELOPMENT.md), [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) |

## Kapsam Dışı Bırakılanlar

| Konu | Karar | Gerekçe |
|---|---|---|
| OCR | Uygulanmadı | Ödev taranmış belgenin *doğrulamada yakalanmasını* istiyor; sistem bunu net hata mesajıyla reddediyor (FR-08). |
| Vector database / RAG | Uygulanmadı | Retrieval gerektiren bir belge koleksiyonu yok; her CV oturum içinde yükleniyor ve normalize profile dönüşüyor. Bkz. [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md). |
| Encryption-at-rest | Uygulanmadı | Demo kapsamı; bilinçli sınır olarak [SECURITY.md](../SECURITY.md)'de belgelendi. |
