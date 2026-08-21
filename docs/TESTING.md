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

Toplam **155 test**, 18 dosyada. (Test sayısının tek kaynağı bu
dokümandır; diğer dosyalar sayı tekrar etmez ki eskimesinler.)

| Dosya | Test | Neyi doğrular |
|---|---:|---|
| `test_cv_layouts.py` | 7 | Beş farklı PDF layout'unun (tek kolon, iki kolon, tablo, farklı bölüm sırası, çok sayfalı) okunabildiği ve içeriğinin korunduğu |
| `test_pdf_parser.py` | 16 | 6 doğrulama senaryosu (boş/imza/bozuk/şifreli/sayfasız/metinsiz), farklı layout'lar (tek sütun, iki sütun, çok sayfa, tablo), kırpma sınırı ve tam-sınır durumu |
| `test_criteria_service.py` | 20 | Serbest metinden kriter çıkarımı, açık listede tamlık kontrolü, tek-kriter doğal dil toleransı, semantik duplicate önleme, sıkı grounding, intent modeli override'ı, niyet belirlenemezse açık hata |
| `test_models.py` | 12 | Pydantic şemaları, `extra="forbid"`, kanıtsız yüksek puan reddi, çıktı sözleşmesi sınırları (rank sıralılığı, skor aralığı, status) |
| `test_sqlite_repo.py` | 11 | Kalıcılık, sohbet geçmişi ve TTL temizliği, özet ilerlemesi, atomik pending-file ekleme ve sahiplenme (TOCTOU) |
| `test_batch_analysis.py` | 7 | 5 CV limiti, all-or-nothing ön doğrulama, top-3 sözleşmesi, kırpma bilgisinin JSON şemasını kirletmemesi |
| `test_cv_analysis_service.py` | 16 | Kriter kimliği; çift-kaynak kanıt ve güvenli skor düşürme; diller arası kriter toleransı; uydurma sayı/beceri filtreleme; evaluator'a ham metin sızmaması; batch context bütçesi |
| `test_openai_compatible_client.py` | 6 | LM Studio/vLLM uyumlu istemci, `response_format` sözleşmesi, retry, Bearer token |
| `test_chat_service.py` | 5 | Sıcak pencere + rolling summary, özetleme hatasında veri kaybı olmaması |
| `test_config.py` | 6 | Backend seçimi, geçmiş saklama varsayılanı, geçersiz değer reddi, zorunlu token |
| `test_scoring.py` | 5 | Ortalama hesaplama, top-3 sıralama, eşitlik durumu |
| `test_handlers.py` | 10 | Telegram akışı, Markdown fallback, kırpma uyarısı, atomik analiz kuyruğu, reset/sohbet/kriter yarışları, sohbet sırası/kilit davranışı |
| `test_media_group_collector.py` | 6 | Albüm toplama, debounce, limit, kapatılmış gruba geç gelen dosya |
| `test_formatter.py` | 3 | Markdown rapor, JSON çıktı biçimi |
| `test_ollama_client.py` | 2 | `/api/chat` sözleşmesi, şema retry'ı |
| `test_grounding.py` | 9 | Aday adı ve kanıt kaynak-doğrulama: aksan/kopya toleransı; uydurma terim ve sayı reddi |
| `test_acceptance_matcher.py` | 12 | Kabul testi kriter eşleştiricisi — eksik etiket reddi, Türkçe çekim ve PDF örneğindeki anlamsal alias toleransı |
| `test_router.py` | 2 | Eşzamanlı update kabulü ve açılışta veri yaşam döngüsü temizliği |

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
| `test_free_text_without_keyword_can_define_criteria` | Anahtar-kelime kısayolu denendi; bu test onu anında kırdı ve yaklaşım geri alındı |
| `test_more_than_five_cvs_is_rejected_before_processing` | 5 CV limiti LLM'e gitmeden önce uygulanmalı |
| `test_batch_uses_two_llm_calls_and_scores_only_normalized_profiles` | Ham CV metninin evaluator prompt'una sızmaması (ödevin çekirdek şartı) |
| `test_model_corrupted_turkish_name_is_rejected` / `test_corrupted_candidate_name_triggers_retry_and_is_fixed` | Canlı koşuda model Türkçe aksanlı ismi bozdu; bozuk ad sessizce rapora giriyordu |
| `test_late_file_after_group_is_processed_is_rejected` | 5 dosya dolup grup işlendikten sonra geç gelen 6. update yeni bir batch başlatabiliyordu |
| `test_intent_failure_retries_with_main_model` / `test_intent_failure_on_both_models_raises_explicit_error` | Küçük intent modeli JSON üretemeyince kullanıcının kriter tanımı sessizce sohbete düşüyordu; artık ana modelle tekrar denenir, o da başarısızsa `IntentUndecidableError` |
| `test_natural_language_path_shares_grounding_correction` | Grounding düzeltmesi yalnız `/criteria` yolunda çalışıyordu; komutsuz (asıl) akış uydurma kriteri doğrudan kaydedebiliyordu |
| `test_semantically_grounded_paraphrase_is_accepted` | PDF'de olmayan bir birebir-etiket kısıtı eklenmişti; parafrazı reddedip gereksiz düzeltme turu tetikliyordu |
| `test_drops_partially_grounded_label_with_unrequested_terms` | Tek ortak kelime, modelin etikete kullanıcıdan gelmeyen Kubernetes/liderlik gibi kavramlar eklemesini engellemiyordu |
| `test_completeness_does_not_treat_single_criterion_prose_as_missing_terms` | Tek kriteri anlatan "konusunda/yıl/arıyorum" gibi doğal dil kelimeleri yanlışlıkla ayrı kriter sayılıyordu |
| `test_intent_and_extractor_semantic_duplicate_is_saved_once` | Intent ve extractor aynı ölçütü çekim farkıyla iki kez kaydedebiliyordu |
| `test_natural_language_criteria_uses_dedicated_extraction_before_save` | Intent+extraction birleşik çıktısı bazı modellerde kriter atlıyordu; criteria niyetinde özel extractor her zaman çalışmalı |
| `test_partial_extraction_retries_and_combines_grounded_criteria` / `test_intent_and_extractor_partial_results_are_combined_before_missing_retry` | LM Studio kısmi listeler ürettiğinde grounded sonuçlar birleştirilmeli, eksik kaynak terimleri için tek düzeltme turu yapılmalı |
| `test_high_score_evidence_must_exist_in_normalized_profile` | Profile dayanmayan serbest evidence yüksek skorla kabul ediliyordu; artık skor 0'a iner |
| `test_high_score_rejects_evidence_with_one_real_and_one_invented_claim` | Tek gerçek kelime uydurma iddiayı maskeleyebiliyordu |
| `test_cross_language_criterion_accepts_fully_source_grounded_evidence` | Türkçe dinamik kriter ile İngilizce CV kanıtı arasında sözlüksel ortak kelime olmaması doğru kanıtı reddedebiliyordu |
| `test_high_score_rejects_invented_numeric_claim` | Kanıttaki uydurma "10 yıl" ifadesinin sayısı kelime filtresinde atlanabiliyordu |
| `test_high_score_evidence_must_exist_in_raw_source_not_only_profile` / `test_ungrounded_extracted_skill_is_removed_from_normalized_profile` | LLM'in normalize profile eklediği ama PDF'de olmayan bilgi kanıtı ve skoru meşrulaştırabiliyordu |
| `test_batch_downgrades_cross_candidate_evidence_instead_of_aborting` | Batch modelinin bir adaydan diğerine taşıdığı kanıt tüm analizi düşürüyor veya Top-3 skorunu etkileyebiliyordu |
| `test_take_pending_files_claims_snapshot_atomically` | Eşzamanlı iki `/analyze` aynı kuyruğu iki kez işleyebiliyor, analiz sırasında yüklenen dosya son temizlikte silinebiliyordu |
| `test_reset_waits_for_in_flight_chat_before_clearing_history` | Devam eden LLM yanıtı `/reset` sonrasında eski mesajı geçmişe geri yazabiliyordu |
| `test_reset_waits_for_in_flight_criteria_command_before_clearing` / `test_reset_waits_for_in_flight_caption_criteria_before_clearing` | Devam eden kriter çıkarımı reset tamamlandıktan sonra eski kriterleri yeniden yazabiliyordu |
| `test_bot_still_answers_chat_while_batch_is_running` | Ödevin "batch sırasında bot yanıt vermeli" şartı: kilitler birleştirilirse bu test timeout'a düşer |
| `test_every_layout_is_readable_and_keeps_key_content` | Beş mock CV aynı şablonla üretiliyordu; "farklı format" şartı hiç test edilmiyordu |
| `test_qualitative_report_sections_cannot_be_empty` | Kabul testi gerçek modelde yakaladı: rapor bölümleri boş gelebiliyor, kullanıcı "(belirtilmedi)" görüyordu |
| `test_label_matching` | Kabul testi eşleştiricisi fazla toleranslıydı: "React" etiketi "React tecrübesi" beklentisini PASS ediyordu |
| `test_same_chat_messages_are_processed_in_arrival_order` | Niyet sınıflandırması kilit dışındaydı; aynı sohbetten hızlı gelen iki mesaj sohbet geçmişine ters sırada yazılabiliyordu |
| `test_batch_budget_trims_only_when_total_exceeds_limit` | 5 × 20.000 karakterlik batch prompt'u yerel modelin context window'unu taşırabiliyordu |

## CI

`.github/workflows/ci.yml` her push ve PR'da çalışır:

```
ruff check      →  lint + import sırası
mypy            →  tip denetimi
compileall      →  sözdizimi
pytest          →  155 test (Python 3.13 ve 3.14 matrisi)
pip check       →  bağımlılık tutarlılığı
```

`main` korumalıdır: normal kullanıcılar için bu kontroller ve bir onay
zorunludur. Tek geliştiricili bakım/kurtarma yolu için repository admin bypass'ı
açıktır; bu istisna GitHub ayarında ve burada açıkça belirtilir.

## Kabul Testi (Gerçek Model)

`scripts/validate_assignment.py` ödev PDF'indeki senaryoyu **gerçek** model
sunucusuna karşı çalıştırır. Otomatik testlerden farklı bir soruyu yanıtlar:
*"yapılandırılmış model ödevin gerçek senaryosunu geçebiliyor mu?"*

```bash
python scripts/validate_assignment.py           # kriterler + tekli CV (~3 dk)
python scripts/validate_assignment.py --full    # + 5 CV batch, top-3 (~15 dk)
```

Kontrol ettikleri:

- Ödev PDF'indeki kriter cümlesi **birebir** kullanılır; mesaj kriter olarak
  sınıflandırıldı mı
- **Kriter eksiksizliği: 3/3** — şema-geçerli olması eksiksiz olduğu anlamına
  gelmez; canlı koşuda bir model üç kriterden yalnız birini çıkarmıştı
- Kriter sayısı tam 3 mü — intent ve extractor aynı ölçütü çekim farkıyla iki
  kez üretirse eksiksizlik kontrolü tek başına bunu yakalayamaz
- Ortak JSON şemasına çıkarım (`candidateName`, yetenekler)
- Her kritere puan verildi mi, nitel rapor alanları dolu mu
- `--full`: `processedCVCount`, `topCandidates` sayısı, `rank` sırası,
  `userDefinedCriteria` eşleşmesi, her adayda tüm skorlar
- **Dönen adayların ortalamaları bağımsız yeniden hesaplanır** ve top-3'ün kendi
  içindeki sıralaması doğrulanır — script `scoring.py`'ye güvenmez; aksi halde
  oradaki bir hata testi de yanıltırdı. *Kapsam sınırı:* script yalnız dönen üç
  adayı görür, elenen 4./5. adayın ortalamasını bilmez; top-3 **seçim**
  algoritması `tests/test_scoring.py`'de deterministik test edilir
- `--full` gerçekten 5 mock CV bulunduğunu doğrular (fixture eksikse sessizce
  daha zayıf bir senaryo test edilmiş olurdu)
- Markdown rapor başlıkları (Güçlü Yönler / Zayıf Yönler / Gelişim Tavsiyeleri)
  üretiliyor mu — ek LLM çağrısı gerektirmez

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
