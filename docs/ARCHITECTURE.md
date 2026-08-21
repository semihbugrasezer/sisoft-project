# Mimari

**Pragmatik katmanlı mimari, LLM sağlayıcıları için port soyutlamasıyla.**

Bu doküman dosya haritasını, katman sorumluluklarını, istek akışını ve hata
yayılımını anlatır.

## Gerçek Bağımlılık Yönü

Terminolojide dürüst olmak gerekirse bu tam bir "Clean Architecture" değildir:
`application` katmanı `SQLiteRepo`, PDF parser ve prompt modüllerini doğrudan
import eder. Yalnızca **LLM erişimi** tam ports-and-adapters ile soyutlanmıştır.

```
Presentation (Telegram)
      │
      ▼
Application ──────────────┐
      │                   │
      ▼                   ▼
   Domain           Infrastructure
  (saf mantık)            │
      ▲                   ├── PDF (PyMuPDF)
      │                   ├── SQLite
      │                   └── LLM adaptörleri
      │                            │
      └──── LLMPort ◄───────────────┘
           (arayüz domain'de,
            implementasyon infrastructure'da)
```

Bu bilinçli bir tercihtir: `LLMPort` gerçek bir ihtiyaca dayanır — iki farklı
implementasyon (`OllamaClient`, `OpenAICompatibleClient`) fiilen vardır ve
motor değişimi bir yapılandırma sorunudur. Buna karşılık SQLite ve PDF
parser için tek implementasyon vardır; onlara resmî bir arayüz eklemek bu
ölçekte karşılıksız bir soyutlama olurdu. Testler yine de izoledir: Python'da
duck typing sayesinde sahte (fake) nesneler ayrı bir soyut sınıf tanımlamadan
kullanılabiliyor (bkz. `tests/test_criteria_service.py::FakeRepo`).

## Katmanlar ve Dosyalar

```
app/
├── domain/                 Framework'ten bağımsız, saf iş mantığı
│   ├── models.py           Pydantic şemaları (LLM çıktıları buraya zorlanır)
│   ├── errors.py           AppError hiyerarşisi (PDFValidationError, LLMOutputValidationError, ...)
│   ├── ports.py            LLMPort arayüzü (infrastructure bunu uygular)
│   ├── grounding.py        Kaynak-doğrulama için ortak metin eşleştirme kuralları
│   └── scoring.py          Ortalama hesaplama, top-3 sıralama — LLM'e bağımlı değil
│
├── application/            Use-case servisleri, domain + infrastructure'ı birleştirir
│   ├── chat_service.py     Sohbet + bağlam (sıcak pencere + rolling summary)
│   ├── criteria_service.py Serbest metinden dinamik kriter çıkarımı
│   ├── cv_analysis_service.py   Tekli/batch CV: validate → extract → evaluate
│   └── batch_analysis_service.py  Çoklu CV orkestrasyonu, all-or-nothing ön doğrulama
│
├── infrastructure/         Dış dünya adaptörleri
│   ├── llm/
│   │   ├── ollama_client.py            Ollama /api/chat (qwen2.5:7b)
│   │   ├── openai_compatible_client.py /v1/chat/completions — LM Studio (gemma-4-e4b), vLLM
│   │   └── prompts.py                  Sistem prompt'ları
│   ├── pdf/pymupdf_parser.py           PDF doğrulama + metin çıkarma
│   └── persistence/sqlite_repo.py      Sohbet geçmişi, kriter, pending-file kalıcılığı
│
├── presentation/telegram/  Telegram I/O — iş mantığı burada değil, yalnızca yönlendirme
│   ├── handlers.py          Komut/mesaj handler'ları
│   ├── router.py            Application kurulumu, handler kaydı
│   ├── formatter.py         Markdown rapor + JSON çıktı formatlama
│   └── media_group_collector.py  Albüm (çoklu dosya) toplama + debounce
│
├── config.py                Ortam değişkenleri ve varsayılanlar
└── container.py             Tüm bağımlılıkları tek yerde kurar (DI, framework yok)

main.py                      Entrypoint: config → container → polling
```

## Katman Sorumlulukları

| Katman | Bilir | Bilmez |
|---|---|---|
| `domain` | Pydantic şemaları, saf skorlama fonksiyonları, `LLMPort` arayüzü, hata hiyerarşisi | Telegram, HTTP, veritabanı, dosya sistemi — hiçbir I/O. (Pydantic bir dış bağımlılıktır ama saf bir veri-doğrulama kütüphanesidir; `scoring.py` test edilirken ne LLM ne Telegram gerekir.) |
| `application` | Use-case orkestrasyonu, `domain` modelleri, `LLMPort` | Hangi LLM backend'inin çalıştığını (`OllamaClient` mı `OpenAICompatibleClient` mı) |
| `infrastructure` | httpx, PyMuPDF, sqlite3 — gerçek dış dünya | İş mantığını |
| `presentation/telegram` | Telegram'a özgü I/O, komut yönlendirme, formatlama | İş mantığını — handler her zaman bir application servisini çağırır ve sonucu formatlar |

`container.py` bağımlılıkları tek yerde kurar; framework kullanılmaz, basit
constructor injection yeterlidir.

## Hata Yayılımı

Tüm domain hataları tek bir kökten (`AppError`) türer ve her biri kullanıcıya
gösterilebilir bir `user_message` taşır. Bu, "sessiz yutma yok, teknik
istisna kullanıcıya sızmaz" kuralını mimari seviyede uygular.

```
Telegram Update
      │
      ▼
handlers.py  ──────────────────────────────┐
      │                                     │
      ▼                                     │
Application / Infrastructure                │
      │                                     │
      ├── PDFValidationError                │
      │     "PDF şifreli; şifresiz kopya…"  │
      ├── LLMUnavailableError               │  except AppError:
      │     "Model şu anda yanıt vermiyor…" │    reply(exc.user_message)
      ├── LLMOutputValidationError          │
      │     (tek retry sonrası)             │
      ├── IntentUndecidableError            │
      │     "Kriter mi sohbet mi …"         │
      └── NoCriteriaDefinedError            │
            "Önce kriter tanımlamalısınız…" │
                                            │
      Beklenmeyen istisna ─────────────────┘
            │
            ▼
      error_handler (global)
      logger.exception(...) + genel kullanıcı mesajı
```

İki nokta özellikle önemli:

- **Batch'te all-or-nothing ön doğrulama:** bir dosya bile geçersizse hiçbir dosya LLM'e
  gönderilmez; kısmi sonuç yerine net bir hata döner.
- **Atomik sahiplenme ve temizlik:** `/analyze`, bekleyen CV snapshot'ını SQLite
  lock'u altında alıp kuyruktan çıkarır. Eşzamanlı ikinci analiz aynı dosyaları
  işleyemez; analiz sırasında yüklenen yeni CV'ler sonraki kuyrukta kalır.

## İstek Akışı (Tekli CV Analizi)

```mermaid
sequenceDiagram
    participant U as Kullanıcı
    participant H as handlers.py
    participant CVS as CVAnalysisService
    participant PDF as pymupdf_parser
    participant LLM as LLMPort (Ollama veya LM Studio/vLLM)

    U->>H: PDF gönder
    H->>CVS: analyze(pdf_bytes, criteria)
    CVS->>PDF: validate_and_extract_text()
    PDF-->>CVS: metin (veya PDFValidationError)
    CVS->>LLM: structured_chat(CV_EXTRACTOR_SYSTEM) → CandidateProfile
    CVS->>LLM: structured_chat(CANDIDATE_EVALUATOR_SYSTEM) → EvaluationResult
    CVS-->>H: (profile, evaluation, truncated)
    H-->>U: Markdown rapor
```

Çoklu CV akışı aynı adımları izler, ancak `BatchAnalysisService` önce tüm
dosyaları paralel doğrular (`asyncio.gather`; ilk hatada kesmez — hepsi
biter, sonra tamamı reddedilir) ve LLM extraction/
evaluation'ı CV başına değil tüm belgeler için tek bir toplu istek olarak
çalıştırır. Yalnız eksik/tekrarlı evaluation belgeleri tekli şemayla tamamlanır
ve eksik/tekrarlı kriter kümesi bir kez düzeltilir.

## LLM Backend'leri

Ödev **"Ollama, vLLM veya LM Studio entegrasyonu sağlanmalıdır"** diyor — yani
bunlardan **en az biri** yeterli. Bu proje zorunlu kapsamın ötesine geçip
üçünü de destekler; ikisi tek adaptörle karşılanır:

| Motor | Adaptör | Uç | Durum |
|---|---|---|---|
| Ollama | `OllamaClient` | `/api/chat` (Ollama'ya özgü) | `qwen2.5:7b` ile canlı doğrulandı |
| LM Studio | `OpenAICompatibleClient` | `/v1/chat/completions` | Yerel `google/gemma-4-e4b` ile kriter, tekli CV ve 5-CV Top-3 akışları canlı geçti |
| vLLM | `OpenAICompatibleClient` | `/v1/chat/completions` | Aynı protokol; donanım kısıtı nedeniyle canlı test edilmedi |

**"OpenAI-uyumlu" bir protokol adıdır, servis adı değil.** HTTP biçimini
OpenAI'ın API'si popülerleştirdiği için bu adla anılır; LM Studio ve vLLM kendi
sunucularını bu biçimde sunar. Proje OpenAI servisine bağlanmaz — `openai`
paketi bağımlılık değildir ve istekler `LLM_BASE_URL`'in gösterdiği sunucuya
(varsayılan: `localhost`) gider. Tek adaptörün iki motoru birden karşılamasının
nedeni ikisinin de aynı protokolü paylaşmasıdır; ayrı `LMStudioClient` ve
`VLLMClient` yazmak aynı kodu iki kez yazmak olurdu.

Uzak bir uç yapılandırılırsa CV içeriği o sunucuya gönderilir — bkz.
[SECURITY.md](../SECURITY.md).

## Eşzamanlılık Modeli

| Katman | Mekanizma | Garanti |
|---|---|---|
| Telegram update kabulü | `concurrent_updates(8)` | Bir LLM isteği beklerken diğer update'ler işlenir |
| Sohbet sırası | `chat_id` bazlı ayrı `text` ve `analysis` kilitleri | Aynı tür işlemler sıralı; batch sürerken sohbet açık |
| PyMuPDF / SQLite | `asyncio.to_thread` | Senkron I/O event loop'u bloklamaz |
| Batch PDF doğrulama | `asyncio.gather` | En fazla 5 belge paralel doğrulanır |
| LLM istekleri | `Semaphore(LLM_MAX_CONCURRENCY)` | Tek model sunucusu sınırsız istekle boğulmaz |

`/criteria`, PDF caption kriteri, sohbet ve `/reset` aynı `text` kilidini
kullanır; eski bir LLM çağrısı reset sonrasında veriyi geri yazamaz. CV analizi
ayrı `analysis` kilidindedir. `/analyze`, SQLite kuyruğunu atomik sahiplenir;
eşzamanlı ikinci analiz aynı dosyaları alamaz ve analiz sırasında yeni yüklenen
dosyalar sonraki batch'te kalır.

Batch'te tüm PDF'ler önce paralel ve all-or-nothing doğrulanır. LLM aşaması
nominal olarak iki toplu çağrıdır: extraction ve evaluation. Model bir belgeyi
veya kriteri atlar/tekrarlarsa yalnız sorunlu profil tekli şemayla bir kez
tamamlanır; yine eksikse kısmi Top-3 döndürülmez.

## Temel Tasarım Kararları

| Karar | Gerekçe |
|---|---|
| Ayrı intent, criteria extraction, CV extraction ve evaluation prompt'ları | Hata kaynağı görünür ve her sorumluluk ayrı test edilebilir |
| Ortalama ve Top-3 backend'de | Aritmetik ve sıralama deterministiktir |
| Ham PDF yerine önce `CandidateProfile` | PDF'nin ortak JSON şartı ve prompt-injection sınırı korunur |
| CV başına istek yerine nominal iki batch çağrısı | Tek yerel modelde token tekrarı ve timeout riski azalır |
| Yalnız LLM için port | İki gerçek LLM implementasyonu vardır; tek SQLite/PDF implementasyonu için ek arayüz YAGNI'dir |
| SQLite + rolling summary | Demo kurulumu basit kalır, prompt penceresi sınırlıyken uzun bağlam korunur |
| Vector DB yok | Retrieval yapılacak kalıcı CV koleksiyonu bulunmaz |

Anahtar-kelimeyle kriter intent'ini atlama yaklaşımı testte reddedildi: “React
tecrübesi benim için önemli” geçerli bir serbest-metin kriteridir. Bu yüzden
niyet structured output ile belirlenir; gecikme gerektiğinde isteğe bağlı
`LLM_INTENT_MODEL` ile azaltılır.

## Bilinen Mimari Kısıtlar

- **Tek instance varsayımı** — SQLite ve bellek içi kilitler/albüm tamponu tek
  process varsayar; yatay ölçekleme için paylaşılan bir state store gerekir.
- **Batch LLM aşaması CV başına paralel değil** — tek yerel model için nominal
  iki toplu çağrı kullanılır; yalnız eksik belge/kriterler dar kapsamlı retry alır.
- **20.000 karakter extraction sınırı** — çok uzun CV'ler kırpılır; kullanıcı
  uyarılır.
- **Encryption-at-rest yok** — bkz. [SECURITY.md](../SECURITY.md). Sohbet geçmişi
  ve bekleyen CV'ler sırasıyla `CHAT_RETENTION_HOURS` ve `CV_RETENTION_HOURS`
  ile açılışta temizlenir; bu, kesintisiz çalışan süreçte kesin üst sınır değildir.
