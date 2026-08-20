# AI Destekli Geliştirme Süreci

Ödev, yeni nesil AI araçlarının aktif kullanılmasını açıkça istiyor ve
değerlendirmenin *"kodu AI mi yazdı"* üzerinden değil, **üretilen mimariye ve
koda ne kadar hâkim olunduğu** üzerinden yapılacağını belirtiyor. Bu doküman
sürecin nasıl yürütüldüğünü ve insan denetiminin nerede devreye girdiğini
anlatır.

## Kullanılan Araçlar

| Araç | Rol |
|---|---|
| **Claude Code** | Asıl implementation; katman katman kod üretimi, refactor, test yazımı |
| **Codex** | İkinci görüş, alternatif implementasyon karşılaştırması |
| **Context7 (`ctx7`)** | Kütüphane dokümantasyonunun doğrulanması — eğitim verisine değil güncel resmî dokümana dayanmak için |

## İş Akışı

```
1. Gereksinim analizi
   PDF maddeleri tek tek çıkarıldı, kapsam ve şema kararları
   KOD YAZILMADAN ÖNCE yazıya döküldü
        ↓
2. Teknoloji seçimi
   Alternatifler lisans/kurulum yükü/olgunluk açısından karşılaştırıldı
   Kütüphane davranışı ctx7 ile resmî dokümandan doğrulandı
        ↓
3. Katman katman implementasyon
   domain → infrastructure → application → presentation
   (bağımlılık yönüne uygun sırayla)
        ↓
4. Bağımsız inceleme
   Standart ve gereksinim uygunluğu ayrı ajanlarla tekrar denetlendi
        ↓
5. Otomatik test
   Her katman için birim/entegrasyon testi (taklit LLM ile)
        ↓
6. Canlı doğrulama
   Gerçek Ollama + gerçek Telegram; bulunan hatalar kök nedene kadar izlendi
```

Adım 1'in amacı özellikle önemliydi: kapsam önceden sabitlenmezse AI araçları
istenmeyen özellikler (vector DB, ayrı frontend, mikroservis) önerme
eğilimindedir. Kapsam dışı bırakma kararları
[DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) ve
[REQUIREMENTS_TRACEABILITY.md](./REQUIREMENTS_TRACEABILITY.md)'de kayıtlıdır.

## İnsan Denetim Noktaları

AI çıktısı doğrudan kabul edilmedi; şu noktalarda insan kararı belirleyici oldu:

| Kapı | Ne denetlendi |
|---|---|
| **Gereksinim uygunluğu** | Üretilen kod PDF'in hangi maddesini karşılıyor? Karşılamıyorsa neden? |
| **Mimari** | Bağımlılık yönü doğru mu? Bir soyutlama gerçekten gerekli mi, yoksa spekülatif mi? |
| **Prompt değişiklikleri** | Prompt "daha iyi göründüğü" için değil, ölçülen bir hatayı düzelttiği için değiştirildi |
| **İstisna yönetimi** | Hata sessizce yutuluyor mu? Kullanıcı anlamlı bir mesaj görüyor mu? |
| **Güvenlik/gizlilik** | CV verisi ne kadar süre saklanıyor? Prompt injection düşünülmüş mü? |
| **Test doğrulama** | Test gerçekten kırılabilir mi, yoksa her durumda geçen bir tautoloji mi? |

## AI Destekli Geliştirmede Yakalanan Gerçek Hatalar

Sürecin işlediğinin kanıtı, üretilen kodda bulunan ve düzeltilen hatalardır.
Hepsi kök nedene kadar izlendi, düzeltildi ve regresyon testiyle korundu:

| Bulgu | Nasıl yakalandı | Düzeltme |
|---|---|---|
| Dil sızıntısı: `hrEvaluation` İngilizce dönüyordu | Canlı koşu #1 | Prompt'a Türkçe talimatı; 3 iterasyon sonra regex ile doğrulandı |
| `"candıdate"` — karışık alfabeli bozuk kelime | Canlı koşu #2 | Prompt'ta "aday" kelimesi zorunlu kılındı |
| Telegram Markdown parse hatası — kullanıcı raporu hiç göremiyordu | Gerçek Telegram testi | `BadRequest`'te düz metne düşen fallback + regresyon testi |
| Pending CV'ler istisna durumunda SQLite'ta kalıyordu | Kod incelemesi | `try/finally` ile garantili temizlik |
| Tam-sınır durumunda `truncated` yanlış `False` dönüyordu | Kod incelemesi | Parser'ın sayfa sayısına bakması + regresyon testi |
| Kriter etiketi parafraz ediliyordu (ödev birebir bekliyor) | PDF örnek JSON'u ile karşılaştırma | `_all_labels_exact` + düzeltme turu |
| Anahtar-kelime kısayolu kriter algılamayı bozdu | **Mevcut test paketi anında kırdı** | Yaklaşım geri alındı; yerine opsiyonel `LLM_INTENT_MODEL` |
| 5 CV batch `LLM_TIMEOUT=600`'ü aşıyordu | Canlı koşu #7 | Varsayılan 1200s'ye yükseltildi |
| Dokümantasyon iddiası koddan fazlaydı ("infrastructure arayüzleri uygular") | Bağımsız inceleme | Doküman gerçek duruma göre düzeltildi — karşılıksız soyutlama **eklenmedi** |

Son satır özellikle önemli: incelemede "mimarin dokümanla uyuşmuyor" denince
iki seçenek vardı — dokümanı düzeltmek veya kodu dokümana uydurmak için port
soyutlamaları eklemek. Tek implementasyonu olan bir bağımlılık için resmî
arayüz eklemek bu ölçekte karşılıksız bir soyutlama olacağından **doküman
düzeltildi, kod olduğu gibi bırakıldı.**

## Kabul Edilen ve Reddedilen Öneriler

AI araçlarının ve bağımsız incelemelerin her önerisi uygulanmadı. Örnekler:

**Kabul edilenler:** `try/finally` ile CV temizliği, truncation sınır
düzeltmesi, jenerik `LLM_*` konfigürasyon adları, mypy'ın CI'a eklenmesi,
dokümantasyon doğruluk düzeltmeleri.

**Reddedilenler ve gerekçeleri:**

| Öneri | Neden reddedildi |
|---|---|
| CV başına paralel LLM isteği | Tek yerel model GPU'da zaten seri işliyor; N istek gerçek paralellik getirmez, token maliyetini ve timeout riskini artırır. Ölçülmüş, çalışan bir tasarımı bozardı. |
| `candidateName` için grounding validator | Tek bir gözlemlenen örnek üzerine kural yazmak aşırı-uydurma (overfitting) olurdu; bilinen sınırlama olarak belgelendi. |
| Vector database / RAG | Retrieval gerektiren belge koleksiyonu yok. |
| Kalıcı `development` branch | Tek geliştiricili projede gereksiz ikinci entegrasyon noktası. |
| Coverage eşiği (%90 vb.) | Ölçülmeden konan yüzde kozmetik; testler risk alanlarına göre yazıldı. |

## Sonuç

AI araçları bu projede **implementation hızlandırıcı** olarak kullanıldı.
Gereksinim yorumu, mimari kararlar, trade-off analizi, test tasarımı, canlı
doğrulama ve kabul sorumluluğu geliştiricide kaldı. Yukarıdaki hata tablosu
ve reddedilen öneriler listesi, üretilen kodun körü körüne kabul edilmediğinin
kaydıdır.
