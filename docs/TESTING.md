# Test Stratejisi

İki ayrı doğrulama katmanı vardır:

1. **Otomatik testler** (bu doküman) — hızlı, deterministik, CI'da her
   commit'te çalışır. LLM taklit (fake) nesnelerle değiştirilir.
2. **Canlı doğrulama** ([VALIDATION.md](./VALIDATION.md)) — gerçek model
   sunucusuna ve gerçek Telegram'a karşı, elle yürütülen koşular.

İkisi farklı soruları yanıtlar: otomatik testler *"kod sözleşmelere uyuyor
mu?"*, canlı koşular *"gerçek bir model bu sözleşmeleri karşılayabiliyor mu?"*.

## Çalıştırma

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
ruff check app main.py tests scripts
mypy app main.py
```

## Kapsam

Toplam **106 test**, 16 dosyada. (Test sayısının tek kaynağı bu
dokümandır; diğer dosyalar sayı tekrar etmez ki eskimesinler.)

| Dosya | Test | Neyi doğrular |
|---|---:|---|
| `test_pdf_parser.py` | 16 | 6 doğrulama senaryosu (boş/imza/bozuk/şifreli/sayfasız/metinsiz), farklı layout'lar (tek sütun, iki sütun, çok sayfa, tablo), kırpma sınırı ve tam-sınır durumu |
| `test_criteria_service.py` | 13 | Serbest metinden kriter çıkarımı, grounding, birebir etiket retry'ı (hem `/criteria` hem doğal dil akışında), intent modeli override'ı, niyet belirlenemezse açık hata |
| `test_models.py` | 8 | Pydantic şemaları, `extra="forbid"`, kanıtsız yüksek puan reddi, çıktı sözleşmesi sınırları (rank sıralılığı, skor aralığı, status) |
| `test_sqlite_repo.py` | 9 | Kalıcılık, sohbet geçmişi, özet ilerlemesi, atomik pending-file ekleme (TOCTOU) |
| `test_batch_analysis.py` | 7 | 5 CV limiti, all-or-nothing ön doğrulama, top-3 sözleşmesi, kırpma bilgisinin JSON şemasını kirletmemesi |
| `test_cv_analysis_service.py` | 8 | Kriter kimliği zorlaması, ham metnin evaluator'a sızmaması, batch context bütçesi |
| `test_openai_compatible_client.py` | 6 | LM Studio/vLLM uyumlu istemci, `response_format` sözleşmesi, retry, Bearer token |
| `test_chat_service.py` | 5 | Sıcak pencere + rolling summary, özetleme hatasında veri kaybı olmaması |
| `test_config.py` | 5 | Backend seçimi, geçersiz değer reddi, zorunlu token |
| `test_scoring.py` | 5 | Ortalama hesaplama, top-3 sıralama, eşitlik durumu |
| `test_handlers.py` | 5 | Telegram akışı, Markdown fallback, kırpma uyarısı, büyük JSON'un dosya olarak gönderilmesi, sohbet sırası/kilit davranışı |
| `test_media_group_collector.py` | 6 | Albüm toplama, debounce, limit, kapatılmış gruba geç gelen dosya |
| `test_formatter.py` | 3 | Markdown rapor, JSON çıktı biçimi |
| `test_ollama_client.py` | 2 | `/api/chat` sözleşmesi, şema retry'ı |
| `test_grounding.py` | 7 | candidateName kaynak-doğrulama: aksanlı isim bozulması, uydurma ad, sıralama/büyük-küçük harf toleransı |
| `test_router.py` | 1 | Eşzamanlı update kabulü |

## Neyin Taklit Edildiği (ve Neyin Edilmediği)

| Bileşen | Testte | Gerekçe |
|---|---|---|
| LLM istemcisi | **Taklit** (fake sınıf, `structured_chat` implemente eder) | Gerçek model yavaş (dakikalar) ve deterministik değil — CI'da kullanılamaz |
| SQLite | **Gerçek** (geçici dosya) | Kütüphane hızlı; gerçek SQL davranışını (atomiklik, WAL) taklit etmek yanlış güven verirdi |
| PyMuPDF | **Gerçek** | PDF üretip okumak hızlı; asıl test edilen şey kütüphanenin gerçek davranışı |
| Telegram Bot API | **Taklit** (`SimpleNamespace` bot nesnesi) | Ağ çağrısı gerektirir; handler mantığı ondan bağımsız test edilebilir |

Test PDF'leri çalışma anında `pymupdf` ile üretilir (`_layout_pdf`) —
repository'ye binary fixture eklemek yerine. Böylece hangi layout'un test
edildiği kodda okunabilir kalır.

## Regresyon Testleri

Bazı testler doğrudan gerçek bir hatadan doğdu; isimleri o hatayı anlatır:

| Test | Hangi hatayı korur |
|---|---|
| `test_single_analysis_report_falls_back_to_plain_text_on_bad_markdown` | LLM'in ürettiği dengesiz `*`/`_` Telegram'ın Markdown parser'ını kırıyor, kullanıcı raporu hiç göremiyordu |
| `test_truncated_is_true_only_when_a_page_is_actually_dropped` | Bütçeyi dolduran sayfa son sayfaysa `truncated` yanlışlıkla `False` kalıyordu |
| `test_paraphrased_but_grounded_label_triggers_verbatim_retry` | Model kriter etiketini parafraz edince ödevin beklediği birebir çıktı bozuluyordu |
| `test_free_text_without_keyword_can_define_criteria` | Anahtar-kelime kısayolu denendi; bu test onu anında kırdı ve yaklaşım geri alındı |
| `test_more_than_five_cvs_is_rejected_before_processing` | 5 CV limiti LLM'e gitmeden önce uygulanmalı |
| `test_batch_uses_two_llm_calls_and_scores_only_normalized_profiles` | Ham CV metninin evaluator prompt'una sızmaması (ödevin çekirdek şartı) |
| `test_model_corrupted_turkish_name_is_rejected` / `test_corrupted_candidate_name_triggers_retry_and_is_fixed` | Canlı koşuda model Türkçe aksanlı ismi bozdu; bozuk ad sessizce rapora giriyordu |
| `test_late_file_after_group_is_processed_is_rejected` | 5 dosya dolup grup işlendikten sonra geç gelen 6. update yeni bir batch başlatabiliyordu |
| `test_intent_failure_retries_with_main_model` / `test_intent_failure_on_both_models_raises_explicit_error` | Küçük intent modeli JSON üretemeyince kullanıcının kriter tanımı sessizce sohbete düşüyordu; artık ana modelle tekrar denenir, o da başarısızsa `IntentUndecidableError` |
| `test_natural_language_path_also_enforces_verbatim_labels` | Birebir-etiket düzeltmesi yalnız `/criteria` yolunda çalışıyordu; komutsuz (asıl) akış parafraz edilmiş etiketi doğrudan kaydediyordu |
| `test_same_chat_messages_are_processed_in_arrival_order` | Niyet sınıflandırması kilit dışındaydı; aynı sohbetten hızlı gelen iki mesaj sohbet geçmişine ters sırada yazılabiliyordu |
| `test_batch_budget_trims_only_when_total_exceeds_limit` | 5 × 20.000 karakterlik batch prompt'u yerel modelin context window'unu taşırabiliyordu |

## CI

`.github/workflows/ci.yml` her push ve PR'da çalışır:

```
ruff check      →  lint + import sırası
mypy            →  tip denetimi
compileall      →  sözdizimi
pytest          →  106 test (Python 3.13 ve 3.14 matrisi)
pip check       →  bağımlılık tutarlılığı
```

`main` korumalıdır: bu kontroller geçmeden ve bir onay alınmadan merge
edilemez.

## Kabul Testi (Gerçek Model)

`scripts/validate_assignment.py` ödev PDF'indeki senaryoyu **gerçek** model
sunucusuna karşı çalıştırır. Otomatik testlerden farklı bir soruyu yanıtlar:
*"yapılandırılmış model ödevin gerçek senaryosunu geçebiliyor mu?"*

```bash
python scripts/validate_assignment.py           # kriterler + tekli CV (~3 dk)
python scripts/validate_assignment.py --full    # + 5 CV batch, top-3 (~15 dk)
```

Kontrol ettikleri:

- Serbest metin mesajı kriter olarak sınıflandırıldı mı
- **Kriter eksiksizliği: 3/3** — şema-geçerli olması eksiksiz olduğu anlamına
  gelmez; canlı koşuda bir model üç kriterden yalnız birini çıkarmıştı
- Ortak JSON şemasına çıkarım (`candidateName`, yetenekler)
- Her kritere puan verildi mi, nitel rapor alanları dolu mu
- `--full`: `processedCVCount`, `topCandidates` sayısı, `rank` sırası,
  `userDefinedCriteria` eşleşmesi, her adayda tüm skorlar
- **Ortalamalar ve sıralama bağımsız olarak yeniden hesaplanır** — script
  `scoring.py`'ye güvenmez; aksi halde bir skorlama hatası testi de yanıltırdı

CI'a konmaz: gerçek LLM deterministik değildir ve dakikalar sürer. Bir modelin
"desteklenen" sayılması için bu script'i geçmesi beklenir.

## Bilinçli Olarak Yapılmayanlar

- **Coverage eşiği yok.** Ölçülmeden konan bir yüzde hedefi (örn. "%90")
  gerçek bir kalite sinyali değil, kozmetik bir rakamdır. Testler kapsam
  yüzdesine göre değil, gerçek risk alanlarına (parser, şema doğrulama,
  eşzamanlılık, veri yaşam döngüsü) göre yazıldı.
- **Gerçek LLM'e karşı otomatik test yok.** Deterministik olmadığı ve
  dakikalar sürdüğü için CI'a uygun değil; bunun yerine elle yürütülen canlı
  koşular belgelendi ([VALIDATION.md](./VALIDATION.md)).
- **Gerçek CV fixture'ı yok.** Kişisel veri repository'ye girmemeli; testler
  üretilmiş mock CV'lerle çalışır (`scripts/generate_mock_cvs.py`).
