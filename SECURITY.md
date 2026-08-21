# Güvenlik ve Gizlilik

Bu proje **CV belgeleri ve Telegram sohbet verisi** işler. Bir mülakat/demo
projesidir; üretim ortamı için gerekli sertleştirmeler bilinçli olarak kapsam
dışı bırakılmış ve aşağıda açıkça listelenmiştir.

## Güvenlik Açığı Bildirimi

Güvenlik açıklarını **public issue olarak açmayın**. Bunun yerine
[GitHub Private Vulnerability Reporting](https://github.com/semihbugrasezer/sisoft-project/security/advisories/new)
üzerinden özel bildirim gönderin.

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
| Sohbet geçmişi | SQLite, düz metin | `/reset` ile hemen; ayrıca açılışta `CHAT_RETENTION_HOURS`'tan (varsayılan 168 saat) eski mesajlar silinir |
| Sohbet özetleri (rolling summary) | SQLite, düz metin | `/reset` ile hemen; eski mesajı silinen sohbetin özeti açılış temizliğinde birlikte silinir |
| Kriterler | SQLite, düz metin | `/reset` veya yeni kriter tanımına kadar |
| **CV dosyaları (`/batch` akışı)** | SQLite BLOB | İki katmanlı temizlik: (1) `/analyze`, dosyaları atomik olarak alıp analiz başlamadan kuyruktan çıkarır; analiz sırasında yüklenen yeni dosyalar silinmez; (2) kullanıcı hiç `/analyze`/`/cancel` yazmazsa bir sonraki açılışta `CV_RETENTION_HOURS`'tan (varsayılan 24 saat) eski kayıtlar silinir. Temizlik yalnız açılışta çalıştığı için kesintisiz çalışan bir botta bu bir üst sınır garantisi değildir. |
| CV dosyaları (albüm/tekli yükleme) | Yalnızca bellek | Diske hiç yazılmaz |

## Üretim Öncesi Gerekenler

Bu demo aşağıdakileri **sağlamaz**. Gerçek İK verisiyle kullanmadan önce
eklenmelidir:

- **Encryption-at-rest** — SQLite verisi şifrelenmez.
- **TTL temizliği yalnız açılışta çalışır** — `CHAT_RETENTION_HOURS` ve
  `CV_RETENTION_HOURS` kesintisiz çalışan bir süreçte kesin üst sınır değildir.
  Üretimde zamanlanmış silme işi ve kuruma uygun saklama politikası gerekir.
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
kilidi (lock file) yoktur. GitHub Dependabot uyarıları ve güvenlik güncellemeleri
etkindir; secret scanning ile push protection da repository düzeyinde açıktır.
Üretim dağıtımı için ayrıca `pip-compile`/`uv lock` ile üretilmiş kilit dosyası
ve düzenli güvenlik taraması (`pip-audit`) önerilir.
