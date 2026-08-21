# Deneysel Doğrulama

Doğruluk iddiaları mock veriyle sınırlı kalmasın diye gerçek yerel
`qwen2.5:7b` (Ollama) ve `google/gemma-4-e4b` (LM Studio) sunucularına karşı
canlı çalıştırmalarla test edildi — taklit LLM
istemcileriyle yürütülen otomatik test paketine ek olarak (kapsam ve sayı için
tek kaynak: [TESTING.md](./TESTING.md)). Ana proje tanımı için
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

## 2026-08-21 Bağımsız Audit Tekrarı

Bu tur önceki sonuçlara güvenmek yerine kabul script'ini yeniden çalıştırdı.
Ortam: Python 3.14, Apple M2/16 GB, Ollama `qwen2.5:7b`, LM Studio
`google/gemma-4-e4b`; başlangıç Git commit'i `45faefe` idi. Son hardening
tekrarı `origin/main` `0162d35` tabanlı çalışma ağacında yapıldı. En güncel
Ollama `--full` tekrar koşusu `origin/main` `4ddb059` üzerinde çalıştırıldı.

| Backend / aşama | Sonuç | Süre / not |
|---|---|---|
| Ollama — kriter niyeti + özel extraction | ✅ 3/3 kriter | 97.5s; `React deneyimi`, `Temiz kod yazımı`, `Uzaktan çalışma uyumu` |
| Ollama — tekli CV tam hattı | ✅ PASS | 195.1s; profile extraction, 3/3 skor, nitel bölümler ve Markdown başlıkları geçti |
| Ollama — son `--full` kriter tekrarı | ✅ 3/3, tekrarsız | 129.0s; tam üç kriter çıktı, yakın anlamlı uzaktan-çalışma etiketi çoğaltılmadı |
| Ollama — son `--full` tekli CV tekrarı | ✅ PASS | 247.9s; çift kaynak kanıt grounding, 3/3 skor, dolu nitel bölümler ve Markdown başlıkları geçti |
| Ollama — son `--full` 5-CV batch | ✅ PASS | 991.3s; üç kaynak-dışı skor 0'a indirildi; top-3 ortalamaları bağımsız doğrulandı (`90.0 / 55.0 / 55.0`), nihai JSON şeması geçti |
| LM Studio — ara kriter koşusu (hardening öncesi) | ⚠️ güvenli red | API ve JSON-schema çalıştı; model eksik-terim turunda React'i tekrarladı ve kısmi liste kaydedilmedi |
| LM Studio — güncel kriter + tekli CV | ✅ PASS | 58.7s kriter (3/3, temiz etiketler) + 151.7s tekli CV; ortak JSON, 3/3 skor, nitel bölümler ve Markdown geçti |
| LM Studio — güncel 5-CV batch | ✅ PASS | 1086.6s; ilk batch evaluation'da eksik/tekrarlı `documentId=1..4` yalnız ilgili profiller için tekli retry ile tamamlandı. Top-3 ortalamaları (`78.33 / 76.67 / 58.33`) bağımsız doğrulandı ve nihai JSON şeması geçti |

Audit sırasında kabul ölçerinin yalnız çekim farklarını tanıyıp PDF'nin açıkça
izin verdiği anlamsal eşdeğerleri (`tecrübe`/`deneyim`, `temiz kod`/`Clean Code`)
yanlış FAIL saydığı da görüldü. Ölçer bu sınırlı alias'ları tanıyacak şekilde
düzeltildi; eksik `React` gibi etiketler hâlâ reddedilir.

İlk evidence-grounding denemesi yalnız profile ait tek bir somut kelimeyi yeterli
saydığı için "React ve uydurma Kubernetes" gibi karma bir iddia geçebiliyordu.
Güncel kural, yüksek skor kanıtındaki tüm somut terimleri hem normalize profile
hem ham PDF kaynak metnine karşı doğrular. Aksan ve tek karakterlik kopya
sapması kabul edilirken yeni terim ve sayılar reddedilir. Kaynakta bulunmayan
extraction becerileri profile alınmaz; iki kaynağa dayanmayan skor tüm batch'i
iptal etmek yerine `0 / Kanıt yok` değerine indirilir. Son `--full` koşusu,
batch modelinin üç kaynak-dışı kanıtını güvenli düşürüp kalan sonuçla geçerli
top-3 JSON ürettiğini doğruladı.

## Bulunan Sorunlar ve Düzeltme Geçmişi

| # | Koşu | Süre (batch) | Bulgu | Aksiyon |
|---|---|---|---|---|
| 1 | Tam akış (kriter + tekli + batch) | 580s | Kriter etiketi parafraz edildi: "React tecrübesi" → "React deneyimi". `_grounded_criteria` konu değişmediği için bunu kabul eder — kasıtlı tasarım. `hrEvaluation` alanı tamamen İngilizce döndü. | `CRITERIA_EXTRACTOR_SYSTEM`'daki "birebir" ifadesi yumuşatıldı. `CANDIDATE_EVALUATOR_SYSTEM`'a "çıktı Türkçe olsun" talimatı eklendi. |
| 2 | Yalnız batch (Türkçe-fix testi) | 463.5s | Cümle yapısı Türkçeleşti ama `"candıdate"` kelimesi kaldı — düz İngilizce bile değil, karışık alfabeli bozuk bir kelime. | Prompt'a "'candidate' yerine 'aday' de" talimatı eklendi (2. iterasyon). |
| 3 | Yalnız batch (candidate-fix testi) | 476.7s | Regex ile otomatik ölçüldü (Kiril script + `\bcandidate\b`): üç adayda da `mixed_script=False`, `english_leak=False`. | **Temiz.** Örnek: *"Bu aday, React deneyimine sahip ve uzaktan çalışma uyumlu bir profesyoneldir..."* |
| 4 | Rolling summary (ayrı koşu, aşağıda) | 84.0s (chat) | — | Rolling summary mekanizması doğrulandı. |
| 5 | Model-kapasitesi sınırı (LM Studio, `qwen2.5-0.5b-instruct`) | — | Küçük model, serbest metin intent-classification'da şemaya uygun JSON'u iki denemede de üretemedi; kullanıcı `LLMOutputValidationError`'ın kontrollü hata mesajını gördü. | Entegrasyonun kendisi doğru çalıştı (hata yakalandı, retry denendi, kullanıcıya çökme yerine anlaşılır mesaj döndü) — darboğaz model kapasitesiydi, kod değil. Bot varsayılan Ollama yapılandırmasına geri alındı. **Bu teşhis daha sonra koşu #8'de doğrulandı:** aynı backend, 4B'lik bir modelle aynı adımı sorunsuz geçti. |
| 6 | Gerçek (anonimleştirilmiş) bir CV, Türkçe aksanlı karakterler içeriyor (tekli analiz, canlı Telegram) | ~2-3 dk | Sohbet bağlamı, dinamik kriter tanımlama ve tekli CV Markdown raporu uçtan uca doğru çalıştı. Ancak `candidateName` alanında harf yer değiştirmesi gözlendi (ör. "ğ" içeren bir isimde iki harf yer değiştirdi) — Türkçe aksanlı karakterlerde model kaynaklı bir hata. | **Çözüldü.** Prompt zaten "birebir aktar" diyordu; prompt'a güvenmek yetmedi. `is_grounded_in_source` (app/domain/grounding.py) ile deterministik kaynak-doğrulama eklendi: ad kaynak metinde geçmiyorsa bir düzeltme turu denenir, yine tutmazsa alan None'a çekilir ve çağıran dosya adına düşer. Bozulmuş ad artık rapora taşınmaz. |
| 7 | 5 gerçek CV batch analizi (canlı Telegram, `LLM_TIMEOUT=1200`) | 852.0s (259.6s extraction + 592.4s evaluation) | `MultiAnalysisResponse` şemasına birebir uyan top-3 JSON döndü; sıralama (90.0/85.0/85.0) doğru, `hrEvaluation` temiz Türkçe, mixed-script/English leak yok. Önceki bir koşuda `LLM_TIMEOUT=600` evaluation adımını yarıda kesmişti (`LLMUnavailableError`, kontrollü hata mesajı — kod hatası değil). | `LLM_TIMEOUT` 600 → 1200 yükseltildi; bu donanımda batch evaluation tek başına 600s'yi aşabiliyor. Sonraki koşu sorunsuz tamamlandı. |
| 8 | **LM Studio + `google/gemma-4-e4b` (4B), ilk uçtan uca koşu** — koşu #5'in protokol boşluğunu kapatır | 25.7s + 3.9s + 115.1s | Üç aşama protokol düzeyinde çalıştı. `candidateName` doğru ("Caner Bulut"), skills doğru, `hrEvaluation` temiz Türkçe. **Tarihsel kalite bulgusu:** üç kriterlik girdiden yalnızca bir kriter çıktı. | Bu bulgu kısmi extraction ve batch tamlık kontrollerinin eklenmesine yol açtı. Güncel kriter, tekli CV ve 5-CV Top-3 sonuçları yukarıdaki audit tablosundadır. |

> **Not (Koşu 1 hakkında güncelleme):** 1. koşuda gözlenen parafraz kabulü
> ("React tecrübesi" → "React deneyimi") kasıtlı bir tasarım tercihiydi. Bir ara
> "PDF birebir etiket bekliyor" yorumuyla birebir zorunluluğu eklendi; **bu
> yorum yanlıştı ve geri alındı** — PDF'in kendi JSON örneği
> `userDefinedCriteria` içinde `"Clean Code"` gösterirken düz metin örneğinde
> kullanıcı "temiz kod yazımı" yazıyor, yani birebir kopya bir sözleşme değil.
> Bugünkü davranış: kriter kullanıcının metnine **grounded** olmalı (uydurma
> reddedilir), ama parafraz kabul edilir.

Girdi metni toplamda yalnızca ~834 token (5 mock CV, ilk üç koşu). Ölçülen süre
CV boyutundan gelmez; kaynağı 5 iç içe `CandidateProfile`/`evaluation`
nesnesinin kısıtlı JSON şemasıdır:

- Kriter çıkarımı: ~70 saniye.
- Tekli CV analizi (extraction + evaluation, 2 LLM çağrısı): ~180 saniye.
- 5 CV batch (Ollama nominal extraction + evaluation, 2 LLM çağrısı): altı ölçüm —
  580s / 463.5s / 476.7s / 852s / 1003.8s / **991.3s**. Yani **~8-17
  dakika** aralığı; en güncel `--full` koşusu 991.3s = 16.5 dakikadır.

## OpenAI-Uyumlu Backend (LM Studio) — Uçtan Uca Doğrulama

`openai_compatible` backend'i iki ayrı seviyede doğrulandı.

**Protokol seviyesi** (koşu #5 dönemi): `OpenAICompatibleClient.structured_chat()`
gerçek bir LM Studio sunucusuna karşı çağrıldı, dönen JSON doğrulanmış bir
Pydantic nesnesine dönüştü (1.4s). Bu yalnızca `response_format: json_schema`
sözleşmesini test eder — model kalitesini değil.

**Uygulama seviyesi** (koşu #8): `google/gemma-4-e4b` (4B, 34k context)
yüklenip projenin **gerçek servisleri** üzerinden çalıştırıldı — mock yok,
`CriteriaService` ve `CVAnalysisService` doğrudan çağrıldı:

> Aşağıdaki tablo düzeltme öncesi tarihsel koşudur. Güncel tam kabul
> sonuçları bu belgenin başındaki 2026-08-21 audit tablosundadır.

| Aşama | Sonuç | Süre |
|---|---|---|
| Kriter çıkarımı (`define_criteria`) | ✅ `['React tecrübesi']` — şema-uyumlu, grounded | 25.7s |
| Sohbet niyeti (`define_if_requested`) | ✅ doğru sınıflandırma: `chat` (kriter üretmedi) | 3.9s |
| Tam CV hattı (`analyze`) | ✅ `candidateName="Caner Bulut"`, skills `[React, TypeScript, Redux, Next.js, Jest]`, skor 90 | 115.1s |

Üretilen değerlendirme: *"Adayın React ve modern frontend teknolojilerindeki
deneyimi çok güçlüdür."* — temiz Türkçe, dil sızıntısı yok.

**Bu koşunun asıl değeri:** koşu #5'te 0.5B modelin iki denemede de
üretemediği yapılandırılmış JSON intent-classification, aynı kodla 4B modelde
sorunsuz çalıştı. "Darboğaz model kapasitesiydi, kod değil" teşhisi böylece
ölçümle doğrulanmış oldu.

**Tarihsel model farkı ve kapatılan kabul boşluğu:** gemma-4-e4b, ilk koşuda üç kriterlik bir
girdiden ("React tecrübesi, temiz kod yazımı, uzaktan çalışma uyumu")
yalnızca birini çıkardı; `qwen2.5:7b` (Ollama) aynı girdiden üçünü de
çıkarıyor. Eski servis şema-uyumlu ve grounded olan bu kısmi listeyi kabul
ediyordu. Güncel servis kaynak kapsamını denetler, eksik parçaları ayrı
structured-output çağrılarıyla tamamlar ve yine eksikse sonucu reddeder. Batch
evaluation'da da yalnız eksik/tekrarlı belge kimlikleri tekli şemayla tamamlanır;
geçerli toplu sonuçlar yeniden üretilmez. Güncel Gemma kriter, tekli CV ve 5-CV
Top-3 koşularını geçti.

**vLLM** ayrıca canlı test edilmedi — Apple Silicon GPU desteklemediği için bu
ortamda çalıştırılamadı. Aynı `response_format` sözleşmesini uyguladığı resmi
dokümantasyonundan doğrulandı (`ctx7`); LM Studio ile kanıtlanan uyumluluk
aynı OpenAI-uyumlu kontratı paylaştığı için geçerlidir.

## Performans Darboğazı ve Optimizasyon Seçenekleri

"Hızlı" göreceli bir kavramdır. Bu ortamda ölçülen profil, gecikmenin baskın
kaynağının mimari değil tek yerel 7B modelin token üretim hızı olduğunu
gösteriyor. Aşağıdaki üç seçenek mimariyi bozmadan uygulanabilir; bu turda
kapsam dışı bırakıldı.

1. **Üretim ortamı: vLLM veya bulut GPU.** Dedicated GPU ve vLLM'in continuous
   batching'i süreyi düşürür. Bunun için ayrı bir adaptör yazmaya gerek yok —
   `OpenAICompatibleClient` zaten vLLM'in OpenAI-uyumlu `/v1/chat/completions`
   kontratını konuşuyor (bkz. [README](../README.md#mimari)). Geçiş yalnızca
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

- **Yerel 7B model gecikmesi** — 5 CV'lik batch analizi bu donanımda ~8–17
  dakika sürer (yukarıdaki ölçümler). Darboğaz
  model/donanımdır, mimari değil.
- **OCR yok** — taranmış/görsel-yalnızca PDF'ler `validate_and_extract_text`
  tarafından "okunabilir metin bulunamadı" hatasıyla reddedilir, OCR ile
  işlenmez. Ödev PDF'i zaten okunamaz belgelerin validation'da yakalanmasını
  istiyor; OCR eklemek bonus olur ama gerekli değil.
- **20.000 karakter extraction sınırı** — çok uzun CV'lerde metin bu sınıra
  kırpılır (context/timeout koruması). Kullanıcı artık Telegram'da bir uyarı
  mesajıyla bilgilendiriliyor (`TRUNCATED_WARNING`, `handlers.py`).
- **Batch'te varsayılan olarak CV başına paralel LLM isteği yok** — bkz.
  [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) "Nominal batch başına iki LLM çağrısı"
  kararı. PDF validation/extraction paraleldir; LLM extraction/evaluation
  tüm belgeler için tek bir toplu istektir (tek yerel model sunucusunu N ayrı
  istekle boğmamak için bilinçli tercih). Yalnız eksik/tekrarlı evaluation
  belgeleri tekli retry alır.
- ~~**Nitel rapor alanları boş kalabiliyor**~~ — **çözüldü.** Kabul testinin ilk
  koşusunda `qwen2.5:7b`, kriterlerin üçünü de doğru puanladığı hâlde
  `strengths`/`weaknesses`/`recommendations` bölümlerinden en az birini boş
  bıraktı; rapor "(belirtilmedi)" ile çıkıyordu. Önce "model kalitesi sınırı"
  diye sınıflandırıldı, ancak ödev PDF §2 bu üç bölümü opsiyonel bırakmıyor —
  yani bu bir **şema sözleşmesi boşluğuydu**. `EvaluationResult` alanlarına
  `min_length=1` eklendi ve prompt'a "gerçek bir zayıf yön yoksa UYDURMA,
  'tespit edilmedi' yaz" kuralı girdi: bölüm dolu kalır, içerik dürüst olur.
  Boş liste artık `ValidationError` → mevcut tek-seferlik düzeltme retry'ı.
- **Aksanlı isimlerde model bozulması** — 7B model Türkçe aksanlı bir ismi
  kopyalarken harf değiştirebiliyor. Kod tarafında kaynak-doğrulama +
  düzeltme turu ile ele alındı (koşu #6); modelin kendisi düzelmedi.
- **Model seçimi bir mimari parametredir** — `qwen2.5-0.5b-instruct` (0.5B)
  yapılandırılmış JSON üretemedi (koşu #5); `google/gemma-4-e4b` (4B) üç
  aşamayı da geçti ama ilk koşuda üç kriterden birini çıkardı (koşu #8).
  Güncel servis eksik kriter/belgeleri dar kapsamlı retry ile tamamladı ve aynı
  model tam kabulden geçti. Model kapasitesi toplam süreyi hâlâ belirgin etkiler.
