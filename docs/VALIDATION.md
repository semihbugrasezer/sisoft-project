# Deneysel Doğrulama

Doğruluk iddiaları mock veriyle sınırlı kalmasın diye gerçek yerel `qwen2.5:7b`
sunucusuna (Ollama) karşı canlı çalıştırmalarla test edildi — mock LLM istemcileriyle
yapılan 89 birim/entegrasyon testine ek olarak. Ana proje tanımı için
[README.md](../README.md)'ye bakın.

## Genel Doğrulanan Davranış

Yeterli kapasitedeki modelle (`qwen2.5:7b`) yapılan tüm koşularda LLM çıktısı
Pydantic şemasına uydu. **İstisna:** 0.5B'lik küçük bir modelle (koşu #5)
şemaya uygun JSON iki denemede de üretilemedi — bu bir kod hatası değil model
kapasitesi sınırıdır ve kullanıcıya kontrollü hata mesajı döndürülerek doğru
biçimde ele alındı.
Concurrency (paralel PDF validation, eşzamanlı Telegram update işleme, chat_id
bazlı kilit) batch işlenirken botu bloklamadı. PDF validation sırası (imza →
açılabilirlik → şifre → sayfa varlığı → okunabilir metin) her adımda doğru hata
mesajı üretti — dört farklı geçersiz PDF senaryosu (`scripts/generate_invalid_cvs.py`)
canlı Telegram üzerinden ayrıca doğrulandı.

## Bulunan Sorunlar ve Düzeltme Geçmişi

| # | Koşu | Süre (batch) | Bulgu | Aksiyon |
|---|---|---|---|---|
| 1 | Tam akış (kriter + tekli + batch) | 580s | Kriter etiketi parafraz edildi: "React tecrübesi" → "React deneyimi". `_grounded_criteria` konu değişmediği için bunu kabul eder — kasıtlı tasarım. `hrEvaluation` alanı tamamen İngilizce döndü. | `CRITERIA_EXTRACTOR_SYSTEM`'daki "birebir" ifadesi yumuşatıldı. `CANDIDATE_EVALUATOR_SYSTEM`'a "çıktı Türkçe olsun" talimatı eklendi. |
| 2 | Yalnız batch (Türkçe-fix testi) | 463.5s | Cümle yapısı Türkçeleşti ama `"candıdate"` kelimesi kaldı — düz İngilizce bile değil, karışık alfabeli bozuk bir kelime. | Prompt'a "'candidate' yerine 'aday' de" talimatı eklendi (2. iterasyon). |
| 3 | Yalnız batch (candidate-fix testi) | 476.7s | Regex ile otomatik ölçüldü (Kiril script + `\bcandidate\b`): üç adayda da `mixed_script=False`, `english_leak=False`. | **Temiz.** Örnek: *"Bu aday, React deneyimine sahip ve uzaktan çalışma uyumlu bir profesyoneldir..."* |
| 4 | Rolling summary (ayrı koşu, aşağıda) | 84.0s (chat) | — | Rolling summary mekanizması doğrulandı. |
| 5 | Model-kapasitesi sınırı (LM Studio, `qwen2.5-0.5b-instruct`) | — | Küçük model, serbest metin intent-classification'da şemaya uygun JSON'u iki denemede de üretemedi; kullanıcı `LLMOutputValidationError`'ın kontrollü hata mesajını gördü. | Entegrasyonun kendisi doğru çalıştı (hata yakalandı, retry denendi, kullanıcıya çökme yerine anlaşılır mesaj döndü) — darboğaz model kapasitesiydi, kod değil. Bot varsayılan Ollama yapılandırmasına geri alındı; `openai_compatible` backend'i 7B+ sınıfı bir modelle kullanılmalı. |
| 6 | Gerçek (anonimleştirilmiş) bir CV, Türkçe aksanlı karakterler içeriyor (tekli analiz, canlı Telegram) | ~2-3 dk | Sohbet bağlamı, dinamik kriter tanımlama ve tekli CV Markdown raporu uçtan uca doğru çalıştı. Ancak `candidateName` alanında harf yer değiştirmesi gözlendi (ör. "ğ" içeren bir isimde iki harf yer değiştirdi) — Türkçe aksanlı karakterlerde model kaynaklı bir hata. | Prompt zaten "candidateName alanına birebir aktar" talimatı içeriyor (`CV_EXTRACTOR_SYSTEM`) — bu bir prompt eksikliği değil, 7B modelin nadir/aksanlı token'larda ad kopyalarken yaptığı bir hallüsinasyon. Kayıtlı bilinen sınırlama; ölçülebilir tek bir örnekle prompt'u aşırı-uydurmak yerine belgelenmesi tercih edildi. |
| 7 | 5 gerçek CV batch analizi (canlı Telegram, `LLM_TIMEOUT=1200`) | 852.0s (259.6s extraction + 592.4s evaluation) | `MultiAnalysisResponse` şemasına birebir uyan top-3 JSON döndü; sıralama (90.0/85.0/85.0) doğru, `hrEvaluation` temiz Türkçe, mixed-script/English leak yok. Önceki bir koşuda `LLM_TIMEOUT=600` evaluation adımını yarıda kesmişti (`LLMUnavailableError`, kontrollü hata mesajı — kod hatası değil). | `LLM_TIMEOUT` 600 → 1200 yükseltildi; bu donanımda batch evaluation tek başına 600s'yi aşabiliyor. Sonraki koşu sorunsuz tamamlandı. |

> **Not (Koşu 1 hakkında güncelleme):** Yukarıdaki 1. koşuda gözlenen parafraz
> kabulü ("React tecrübesi" → "React deneyimi") o tarihte kasıtlı bir tasarım
> tercihiydi. Daha sonra ödev PDF'indeki örnek JSON'un kullanıcının ifadesini
> birebir yansıtmasını beklediği netleşince `CriteriaService.define_criteria`
> bir düzeltme turu daha ekleyecek şekilde sıkılaştırıldı (bkz.
> `_all_labels_exact`, [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md)) — artık
> parafraz edilmiş ama grounded bir label tek turda kabul edilmiyor, önce
> birebir kopya için bir şans daha veriliyor.

Girdi metni toplamda yalnızca ~834 token (5 mock CV, ilk üç koşu). Ölçülen süre
CV boyutundan gelmez; kaynağı 5 iç içe `CandidateProfile`/`evaluation`
nesnesinin kısıtlı JSON şemasıdır:

- Kriter çıkarımı: ~70 saniye.
- Tekli CV analizi (extraction + evaluation, 2 LLM çağrısı): ~180 saniye.
- 5 CV batch (extraction + evaluation, 2 LLM çağrısı): dört ölçüm —
  580s / 463.5s / 476.7s / **852s**. Yani **~8-14 dakika** aralığı; en güncel
  ve tam uçtan uca koşu (#7, gerçek Telegram) 852s = 14.2 dakikadır.
  Diğer dokümanlarda tek bir rakam gerekiyorsa **~14 dakika** (en kötü/en
  güncel ölçüm) kullanılır.

Bu, gerçek bir LM Studio sunucusuna karşı da canlı doğrulandı (mock değil):
`OpenAICompatibleClient.structured_chat()` çağrıldı ve dönen JSON gerçekten
doğrulanmış bir Pydantic nesnesine dönüştü, toplam 1.4 saniyede (protokol
testi — küçük model, kalite testi değil). Ollama'nın kendi
`/v1/chat/completions` ucunun ve vLLM'in aynı `response_format` sözleşmesini
uyguladığı resmi dokümantasyonlarından doğrulandı (`ctx7`); vLLM ayrıca canlı
test edilmedi — Apple Silicon GPU desteklemediği için bu ortamda
çalıştırılamadı.

## Performans Darboğazı ve Optimizasyon Seçenekleri

"Hızlı" göreceli bir kavramdır. Bu ortamda ölçülen profil, gecikmenin baskın
kaynağının mimari değil tek yerel 7B modelin token üretim hızı olduğunu
gösteriyor. Aşağıdaki üç seçenek mimariyi bozmadan uygulanabilir; bu turda
kapsam dışı bırakıldı.

1. **Üretim ortamı: vLLM veya bulut GPU.** Dedicated GPU ve vLLM'in continuous
   batching'i süreyi düşürür. Bunun için ayrı bir adaptör yazmaya gerek yok —
   `OpenAICompatibleClient` zaten vLLM'in OpenAI-uyumlu `/v1/chat/completions`
   kontratını konuşuyor (bkz. README.md → Teknoloji). Geçiş yalnızca
   `LLM_BACKEND=openai_compatible` + sunucu adresi/model adı yapılandırmasıdır.
   vLLM bu ortamda (Apple Silicon, GPU desteklemiyor) canlı test edilemedi;
   protokol uyumluluğu resmi OpenAI-uyumlu API sözleşmesinden doğrulandı.
2. **Daha küçük/hızlı model.** Genel modeli `phi3.5` veya `qwen2.5:3b` ile
   değiştirmek doğruluk/hız trade-off'u taşır ve canlı test edilmedi. Daha dar
   kapsamlı bir versiyonu uygulandı ve test edildi: intent-classification
   (kriter mi/sohbet mi) isteğe bağlı ayrı bir model kullanabilir
   (`LLM_INTENT_MODEL`). Değişken boşsa davranış değişmez; ayarlanırsa
   yalnızca günlük sohbetteki ilk sınıflandırma çağrısı hızlanır,
   extraction/evaluation ana modelde kalır.
3. **Paralel per-CV çağrı.** Şu anki "5 CV tek batch çağrıda" tasarımı yerine
   5 eşzamanlı `asyncio.gather` çağrısı kullanılabilir. Ollama sunucusu
   gerçekten paralel işleyebiliyorsa (`OLLAMA_NUM_PARALLEL`) hızlanır; tek
   GPU'da seri işliyorsa fark etmez. Mevcut iki-çağrılı tasarım bilinçli
   tercih edildi çünkü önceki on-çağrılı akış timeout riski taşıyordu (bkz.
   [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md)). Bu geri adım riskli bulundu.

## Dördüncü Koşu — Rolling Summary

Rolling summary ve `LLM_INTENT_MODEL` ilk üç koşudan sonra eklendi. Bu
yüzden ayrı bir dördüncü canlı koşuyla doğrulandı (gerçek `qwen2.5:7b`, toplam
süre 84.0 saniye — düz `chat` çağrıları olduğu için kısıtlı JSON üretiminden
çok daha hızlı). Senaryo: kimlik bilgisi veren bir ilk mesaj, pencereyi
taşıracak kadar dolgu mesaj (`CHAT_HISTORY_LIMIT`=40), sonra artık pencerede
olmayan bilgiyi soran bir mesaj.

```
1) "Merhaba, benim adım Semih ve Python ile backend geliştiriyorum."
   bot: "Merhaba Semih! Python backend geliştirmek için çok güzel bir seçime geldiniz..."
2) [40 dolgu mesaj çifti eklenir — pencere taşar]
3) "Adımı ve ne iş yaptığımı hatırlıyor musun?"
   bot: "Tabii, Semih. Python ile backend geliştirme yaparken..." (64.4s)

DB'deki özet: "Semih, Python ile backend geliştirme yaparken, projeleriniz veya
öğrenmek istediğiniz konular hakkında daha fazla bilgi verirseniz yardımcı olabilirim."
```

Özet doğru bilgiyi (isim ve meslek) yakaladı. Bot bu bilgiyi, artık pencerede
olmamasına rağmen, üçüncü mesajda doğru hatırladı. Aynı davranış ayrıca gerçek
Telegram üzerinden ikinci kez, kullanıcının kendi adı ve React/frontend
bağlamıyla doğrulandı ("adımı hatırlıyor musun" → doğru yanıt).

## Bilinen Sınırlamalar

- **Yerel 7B model gecikmesi** — 5 CV'lik batch analizi bu donanımda ~14
  dakika sürer (ölçüm aralığı 8-14 dk, yukarıya bakın). Darboğaz
  model/donanımdır, mimari değil.
- **OCR yok** — taranmış/görsel-yalnızca PDF'ler `validate_and_extract_text`
  tarafından "okunabilir metin bulunamadı" hatasıyla reddedilir, OCR ile
  işlenmez. Ödev PDF'i zaten okunamaz belgelerin validation'da yakalanmasını
  istiyor; OCR eklemek bonus olur ama gerekli değil.
- **20.000 karakter extraction sınırı** — çok uzun CV'lerde metin bu sınıra
  kırpılır (context/timeout koruması). Kullanıcı artık Telegram'da bir uyarı
  mesajıyla bilgilendiriliyor (`TRUNCATED_WARNING`, `handlers.py`).
- **Batch'te CV başına paralel LLM isteği yok** — bkz.
  [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) "Batch başına iki LLM çağrısı"
  kararı. PDF validation/extraction paraleldir; LLM extraction/evaluation
  tüm belgeler için tek bir toplu istektir (tek yerel model sunucusunu N ayrı
  istekle boğmamak için bilinçli tercih).
- **Örnek modeller kalite değil protokol testi içindir** — `qwen2.5-0.5b-instruct`
  (LM Studio) yalnızca `response_format`/JSON şema sözleşmesini test etmek
  için kullanıldı; üretimde 7B+ sınıfı bir model önerilir.
