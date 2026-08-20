# Güvenlik ve Gizlilik

Bu proje **CV belgeleri ve Telegram sohbet verisi** işler. Bir mülakat/demo
projesidir; üretim ortamı için gerekli sertleştirmeler bilinçli olarak kapsam
dışı bırakılmış ve aşağıda açıkça listelenmiştir.

## Güvenlik Açığı Bildirimi

Güvenlik açıklarını **public issue olarak açmayın**. Bunun yerine repository
sahibine doğrudan ulaşın.

Bildirimde şunları belirtin: etkilenen bileşen, yeniden üretme adımları,
beklenen etki. **Bildirime gerçek CV, Telegram token'ı, API anahtarı veya
kişisel veri eklemeyin.**

## Tehdit Modeli

Sistem üç güvenilmeyen girdi sınırına sahiptir:

| Sınır | Girdi | Savunma |
|---|---|---|
| Telegram | Kullanıcı mesajları, yüklenen dosyalar | Dosya boyutu limiti (15MB), PDF imza/yapı doğrulaması, 5 CV limiti |
| PDF içeriği | Rastgele belge metni | Prompt seviyesinde "veri, komut değil" kuralı; şema doğrulaması; evaluator ham metni görmez |
| LLM çıktısı | Deterministik olmayan model yanıtı | Pydantic şeması (`extra="forbid"`), puan aralığı, kanıt zorunluluğu, tek retry sonrası kontrollü hata |

Ayrıntı: [docs/LLM_PIPELINE.md](docs/LLM_PIPELINE.md) → Prompt Injection.

## Secret Yönetimi

- Tüm secret'lar yalnızca ortam değişkeni ile sağlanır (`.env`).
- `.env` dosyası `.gitignore` içindedir; repository'ye **hiçbir zaman**
  commit edilmemelidir.
- `.env.example` yalnızca placeholder değerler içerir.
- Uzak (remote) bir LLM ucuna `LLM_API_KEY` ile bağlanıyorsanız **HTTPS
  kullanın** — aksi halde bearer token düz metin olarak ağa çıkar.

## Veri Yaşam Döngüsü

| Veri | Nerede | Ne kadar |
|---|---|---|
| Sohbet geçmişi | SQLite, düz metin | `/reset` çağrılana kadar |
| Sohbet özetleri (rolling summary) | SQLite, düz metin | `/reset` çağrılana kadar |
| Kriterler | SQLite, düz metin | `/reset` veya yeni kriter tanımına kadar |
| **CV dosyaları (`/batch` akışı)** | SQLite BLOB | `/analyze` çalıştırılırsa `try/finally` ile her durumda silinir (analiz hata alsa bile). **Ancak:** kullanıcı `/batch` ile dosya yükleyip hiç `/analyze` veya `/cancel` yazmazsa dosyalar süresiz kalır — TTL/otomatik temizlik yoktur. Süreç sert şekilde sonlanırsa (SIGKILL) `finally` de çalışmaz. |
| CV dosyaları (albüm/tekli yükleme) | Yalnızca bellek | Diske hiç yazılmaz |

## Üretim Öncesi Gerekenler

Bu demo aşağıdakileri **sağlamaz**. Gerçek İK verisiyle kullanmadan önce
eklenmelidir:

- **Encryption-at-rest** — SQLite verisi şifrelenmez.
- **Otomatik veri saklama politikası** — sohbet geçmişi `/reset` çağrılmadıkça,
  terk edilmiş `/batch` CV'leri ise `/analyze` veya `/cancel` çağrılmadıkça
  süresiz kalır; TTL/otomatik silme yoktur. Üretimde `pending_files` için
  `expires_at` + açılışta temizlik (ya da CV byte'larını hiç diske yazmamak)
  gerekir.
- **Uzak LLM ucu** — `LLM_BASE_URL` uzak bir sunucuya yönlendirilirse CV metni
  ve sohbet içeriği o sunucuya gönderilir. Varsayılan yapılandırma yereldir;
  uzak uç kullanılacaksa HTTPS ve sağlayıcının veri politikası doğrulanmalıdır.
- **Erişim kontrolü** — bota erişebilen herkes analiz çalıştırabilir; rol veya
  yetkilendirme katmanı yoktur.
- **Denetim kaydı (audit log)** — kimin hangi CV'yi ne zaman analiz ettiği
  yapılandırılmış biçimde tutulmaz.
- **Rate limiting** — kötüye kullanım ve kaynak tüketimi sınırlanmaz.
- **KVKK/GDPR uyumu** — aday verisi işlendiği için yasal dayanak, aydınlatma
  ve silme hakkı süreçleri tanımlanmalıdır.

## Bağımlılıklar

Çalışma zamanı bağımlılıkları alt sınırla (`>=`) tanımlıdır; kesin sürüm
kilidi (lock file) yoktur. Üretim dağıtımı için `pip-compile`/`uv lock` ile
üretilmiş kilit dosyası ve düzenli güvenlik taraması (`pip-audit`) önerilir.
