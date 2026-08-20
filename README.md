# Yapay Zeka Destekli Dinamik Telegram İK ve Sohbet Botu

Kullanıcılarla günlük konularda bağlamı koruyarak sohbet eden, aynı zamanda
konuşma içinde tanımlanan **dinamik kriterlere** göre yüklenen CV'leri analiz
eden bir Telegram botu. Backend Python ile yazılmıştır; katmanlı bir mimariye
(`domain / application / infrastructure / presentation`) sahiptir ve arka
planda **Ollama**, **LM Studio** veya **vLLM**'den herhangi biriyle çalışabilir.

## Özellikler

- **Genel sohbet** — bağlamı (chat history) koruyan, backend'de güvenli
  şekilde yönetilen sohbet akışı.
- **Dinamik kriter tanımlama** — sabit bir kriter listesi yok; kullanıcı
  puanlama kriterlerini serbest metinle tanımlar ("React tecrübesi ve temiz
  kod yazımına göre skorla").
- **Tekli CV analizi** — tek bir CV yüklendiğinde, tanımlı kriterlere göre
  güçlü/zayıf yönler ve gelişim tavsiyeleri içeren okunaklı bir Markdown
  rapor üretir.
- **PDF doğrulama** — bozuk, şifreli, okunamaz veya geçersiz PDF'leri
  backend'de yakalar, kullanıcıya net bir hata mesajıyla döner.
- **LLM Extraction** — ham PDF metni doğrudan skorlanmaz; önce ortak bir
  JSON şemasına (yetenekler, iş deneyimi, eğitim, diller) çevrilir. Tüm
  puanlama ve analiz bu şema üzerinden yürür.
- **Çoklu CV skorlama** — en fazla 5 CV paralel işlenir, dinamik kriterlere
  göre puanlanır, en yüksek ortalamaya sahip ilk 3 aday yapılandırılmış bir
  JSON çıktısı olarak döner.
- **Kilitlenmeyen asenkron altyapı** — Telegram Long Polling üzerinden
  çalışır; çoklu CV işlenirken bot diğer sohbetlere yanıt vermeye devam eder.

## Mimari

```
presentation/telegram/  → Telegram I/O: komutlar, mesaj işleme, formatlama
application/             → use-case servisleri: sohbet, kriter, CV analizi, batch
domain/                  → Pydantic şemaları ve saf iş mantığı (skorlama)
infrastructure/          → LLM istemcileri (Ollama/OpenAI-uyumlu), PDF parser, SQLite
```

Bağımlılıklar tek yönde akar: `presentation → application → domain`;
`infrastructure` bu ikisinin arayüzlerini uygular. `container.py`
bağımlılıkları tek yerde kurar (framework yok, basit constructor injection).

## Teknoloji

- **Python**, `python-telegram-bot` (async, Long Polling)
- **Ollama** (varsayılan) veya **OpenAI-uyumlu** `/v1/chat/completions` ucu
  üzerinden LM Studio / vLLM — `LLM_BACKEND` ile seçilir
- **PyMuPDF** — PDF doğrulama ve metin çıkarma
- **Pydantic** — LLM çıktılarının zorlandığı şemalar
- **SQLite** — sohbet geçmişi ve kriter kalıcılığı

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env içine TELEGRAM_BOT_TOKEN'ı ekleyin (BotFather'dan alınır)

ollama pull qwen2.5:7b   # ilk kurulumda bir kere
```

Çalıştırmadan önce Ollama'nın ayakta olması gerekir (`ollama serve`).

```bash
python main.py
```

## Yapılandırma

`.env` dosyasındaki başlıca değişkenler:

| Değişken | Açıklama |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan alınan token |
| `LLM_BACKEND` | `ollama` (varsayılan) veya `openai_compatible` |
| `OLLAMA_BASE_URL` | LLM sunucu adresi (Ollama, LM Studio veya vLLM) |
| `OLLAMA_MODEL` | Kullanılacak model adı |
| `OLLAMA_MAX_CONCURRENCY` | Sunucuya aynı anda gidebilecek istek sayısı |

`LLM_BACKEND=openai_compatible` ayarlandığında bot, Ollama'nın kendi
`/api/chat` ucu yerine `/v1/chat/completions` üzerinden LM Studio veya vLLM
ile konuşur — `OLLAMA_BASE_URL`/`OLLAMA_MODEL` değişmez, yalnızca farklı bir
sunucuya işaret eder. Application servisleri hangi backend'in çalıştığını
bilmez; ikisi de aynı `LLMPort` arayüzünü uygular (`app/domain/ports.py`).

## Kullanım

1. `/start` — komutları listeler.
2. Serbest metinle kriter tanımla: *"CV'leri React tecrübesi, temiz kod ve
   uzaktan çalışma uyumuna göre değerlendir."*
3. Tek bir CV gönder → detaylı Markdown analiz raporu.
4. 2-5 CV'yi albüm olarak birlikte gönder → otomatik top-3 JSON çıktısı.
   (Tek tek göndermek için `/batch` → PDF'ler → `/analyze`.)
5. `/criteria_show`, `/cancel`, `/reset` — yardımcı komutlar.

## Çıktı Formatı

**Tekli CV:** kriter bazlı skorlar, güçlü yönler, zayıf yönler, gelişim
tavsiyeleri ve genel değerlendirme içeren Markdown rapor.

**Çoklu CV (top-3):**

```json
{
  "status": "success",
  "processedCVCount": 5,
  "userDefinedCriteria": ["React tecrübesi", "Uzaktan çalışma uyumu", "Clean Code"],
  "topCandidates": [
    {
      "rank": 1,
      "candidateName": "Caner Bulut",
      "pdfFileName": "cv_caner_bulut.pdf",
      "dynamicScores": {"React tecrübesi": 95, "Uzaktan çalışma uyumu": 85, "Clean Code": 90},
      "averageScore": 90.0,
      "hrEvaluation": "Aday, tanımlanan dinamik kriterlerin tamamına üst düzey uyum sağlamaktadır."
    }
  ]
}
```

## Test

```bash
python -m pytest tests/ -v
```

Ortalama hesaplama, top-3 sıralama, PDF doğrulama, kriter çıkarımı, sohbet
bağlamı ve Telegram handler'ları için birim/entegrasyon testleri içerir.
Ayrıca gerçek yerel model sunuculara (Ollama, LM Studio) karşı canlı testlerle
doğrulandı.

Mock CV üretimi:

```bash
python scripts/generate_mock_cvs.py   # mock_cvs/ altına 5 örnek CV yazar
```

---

Tasarım kararlarının gerekçeleri, performans ölçümleri ve geliştirme süreci
sunumda ele alınmaktadır.
