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
| FR-02 | Sohbet geçmişi backend'de güvenli yönetilir, bağlam kaybolmaz | `chat_service.py` (sıcak pencere `CHAT_HISTORY_LIMIT`=40 + rolling summary), `sqlite_repo.py` (reset + 168 saatlik açılış temizliği) | `tests/test_chat_service.py`, `tests/test_sqlite_repo.py`; canlı koşu #4 |
| FR-03 | Sabit kriter yok; kullanıcı kriterleri serbest metinle tanımlar | `app/application/criteria_service.py` (LLM intent + extraction, komut zorunlu değil) | `tests/test_criteria_service.py` (özellikle `test_free_text_without_keyword_can_define_criteria`) |
| FR-04 | Kullanıcının tanımladığı kriterlerin tamamı korunur; skorlama bunlara göre yapılır | `criteria_service.py` → intent sonrasında özel extraction + `_grounded_criteria` (kısmi uydurma kriter reddi) | `tests/test_criteria_service.py::test_natural_language_criteria_uses_dedicated_extraction_before_save`, `::test_drops_partially_grounded_label_with_unrequested_terms` |
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
| NFR-03 | Telegram Long Polling veya Webhook | `main.py` → `application.run_polling()` | Otomatik testle kapsanmıyor (bot API'sine gerçek bağlantı gerektirir); canlı Telegram koşularında doğrulandı — bkz. [VALIDATION.md](./VALIDATION.md) |
| NFR-04 | Kilitlenmeyen asenkron mesajlaşma | `router.py` → `concurrent_updates(8)`, `handlers.py` → chat_id bazlı iki ayrı `asyncio.Lock` ailesi | `tests/test_router.py` (eşzamanlı update kabulü), `tests/test_handlers.py::test_same_chat_messages_are_processed_in_arrival_order` ve `::test_different_chats_are_not_serialized_against_each_other`; [CONCURRENCY.md](./CONCURRENCY.md); canlı koşu: batch sırasında bot yanıt vermeye devam etti |
| NFR-05 | LLM motoru entegrasyonu — PDF "Ollama, vLLM **veya** LM Studio" diyor, yani biri yeterli. Bu satır zorunlu gereksinimi karşılar. | `infrastructure/llm/ollama_client.py` (`/api/chat`) | `tests/test_ollama_client.py`; canlı koşu #1-#7 |
| NFR-06 | *(Zorunlu değil — ek yetenek)* vLLM / LM Studio entegrasyonu | `infrastructure/llm/openai_compatible_client.py` (`/v1/chat/completions`) | `tests/test_openai_compatible_client.py`; LM Studio + `gemma-4-e4b` kriter, tekli CV ve 5-CV Top-3 akışlarıyla canlı doğrulandı. vLLM aynı OpenAI-uyumlu kontratı paylaşır ancak bu donanımda ayrıca çalıştırılmadı ([VALIDATION.md](./VALIDATION.md)). |

## Değerlendirme Kriterleri (PDF §Değerlendirme Kriterleri)

Bu bölüm mülakat değerlendirme formundaki dört başlığı doğrudan savunulabilir
kanıta bağlar. “Uygulama” sütunu gerçek akışı, “Doğrulama” sütunu ise iddianın
hangi test veya canlı koşuyla sınandığını gösterir.

| ID | PDF değerlendirme kriteri | Uygulama ve savunma noktası | Doğrulama |
|---|---|---|---|
| EVAL-01 | **Dinamik Prompt Başarısı** | `CriteriaService.define_if_requested` mesajın kriter mi sohbet mi olduğunu structured output ile belirler; kriter niyetinde `define_criteria` özel extraction prompt'unu her zaman çalıştırır. Grounding ve tamlık kontrolünden geçen aynı kriter listesi `CVAnalysisService` tarafından hem tekli `EvaluationResult` hem çoklu `MultiAnalysisResponse` akışına taşınır. Prompt rolleri `prompts.py` içinde ayrıdır; aritmetik ortalama prompt'a bırakılmaz. | `tests/test_criteria_service.py`, `tests/test_cv_analysis_service.py`, `scripts/validate_assignment.py`; [LLM Hattı](./LLM_PIPELINE.md), canlı Ollama kriter + tekli + 5-CV koşusu ([VALIDATION.md](./VALIDATION.md)) |
| EVAL-02 | **PDF Doğrulama & LLM Extraction Kalitesi** | `validate_and_extract_text` boş, PDF imzası olmayan, bozuk, şifreli, sayfasız ve metinsiz belgeleri LLM'den önce keser. Geçerli ham metin `CV_EXTRACTOR_SYSTEM` ile `CandidateProfile` JSON şemasına çıkarılır; evaluator yalnız bu normalize profili görür. Pydantic `extra="forbid"` yapısal sapmayı, grounding katmanı kaynak-dışı ad/beceri/kanıtı engeller. | `tests/test_pdf_parser.py`, `tests/test_cv_layouts.py`, `tests/test_models.py`, `tests/test_grounding.py`, `tests/test_cv_analysis_service.py`; beş farklı mock şablon ve dört geçersiz fixture; [Canlı Doğrulama](./VALIDATION.md) |
| EVAL-03 | **Asenkron Süreç & Bağlam Yönetimi** | `concurrent_updates(8)` farklı update'leri eşzamanlı kabul eder; PyMuPDF ve SQLite çağrıları `asyncio.to_thread` ile event loop dışına taşınır. Aynı sohbette mesaj/kriter/reset sırası `chat_id` bazlı metin kilidiyle korunurken CV analizi ayrı kilit ailesinde çalışır. Son 40 mesaj sıcak pencere, eski bölüm rolling summary olarak backend'de tutulur. | `tests/test_router.py`, `tests/test_handlers.py`, `tests/test_chat_service.py`, `tests/test_sqlite_repo.py`; özellikle batch sürerken sohbet, aynı sohbet sırası ve reset yarış testleri; gerçek Telegram rolling-summary/batch koşuları; [Eşzamanlılık](./CONCURRENCY.md) |
| EVAL-04 | **Vibe Coding Hakimiyeti** | AI araçlarının rolü, insan onay kapıları ve reddedilen öneriler kaydedilmiştir. Katman bağımlılıkları, LLM portu, Pydantic doğrulama, async kilitler, hata hiyerarşisi ve fallback davranışları ayrı belgelerde gerekçelendirilir. Canlı koşuda bulunan dil sızıntısı, Markdown fallback, timeout, grounding ve yarış koşulları regresyon testleriyle kapatılmıştır. | [AI Destekli Geliştirme](./AI_ASSISTED_DEVELOPMENT.md), [Mimari](./ARCHITECTURE.md), [Tasarım Kararları](./DESIGN_DECISIONS.md), [Test Stratejisi](./TESTING.md), [Canlı Doğrulama](./VALIDATION.md) |

## Kapsam Dışı Bırakılanlar

| Konu | Karar | Gerekçe |
|---|---|---|
| OCR | Uygulanmadı | Ödev OCR istemiyor; taranmış/görsel-yalnızca PDF'ler "okunamaz" kategorisine girer ve doğrulamada net bir hata mesajıyla reddedilir (FR-08). |
| Vector database / RAG | Uygulanmadı | Retrieval gerektiren bir belge koleksiyonu yok; her CV oturum içinde yükleniyor ve normalize profile dönüşüyor. Bkz. [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md). |
| Encryption-at-rest | Uygulanmadı | Demo kapsamı; bilinçli sınır olarak [SECURITY.md](../SECURITY.md)'de belgelendi. |
