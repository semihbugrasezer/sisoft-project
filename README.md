# Sisoft — Yapay Zeka Destekli Dinamik Telegram İK ve Sohbet Botu

Mülakat ödevi teslimidir. Mimari kararlar ve kapsam için [`RULES.md`](./RULES.md) tek
doğru kaynaktır.

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env içine TELEGRAM_BOT_TOKEN'ı ekleyin (BotFather'dan alınır)

ollama pull qwen2.5:7b   # ilk kurulumda bir kere
```

## Çalıştırma

```bash
source .venv/bin/activate
python main.py
```

Ollama'nın ayrıca çalışır durumda olması gerekir (`ollama serve`, genelde arka planda
otomatik çalışır — `ollama list` ile kontrol edin).

## Test

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Mock CV üretimi

```bash
python scripts/generate_mock_cvs.py   # mock_cvs/ altına 5 örnek CV yazar
```

## Demo senaryosu

1. `/start` — komutları göster
2. Günlük bir soru sor, sonra "az önce ne sordum?" gibi bağlam gerektiren ikinci soru
3. Komut kullanmadan yaz: "CV'leri React tecrübesi, temiz kod ve uzaktan çalışma
   uyumuna göre değerlendir" → bot kriterleri ayrıştırıp kaydeder
4. `mock_cvs/cv_caner_bulut.pdf`'i tek başına gönder → otomatik, hemen detaylı
   Markdown rapor (komuta gerek yok)
5. Bozuk/şifreli bir PDF gönder → kontrollü hata mesajı
6. `mock_cvs/` altındaki 5 CV'yi **albüm olarak birlikte seçip** gönder → kısa bir
   bekleme sonrası otomatik top-3 JSON (dosyaları tek tek göndermek istersen
   `/batch` → PDF'ler → `/analyze` yedek akışını kullan)
7. Batch işlenirken başka bir sohbetten mesaj gönder → bot kilitlenmeden yanıt verir

## Gereksinimler ve mimari

PDF ile birebir proje gereksinimleri için [`RULES.md`](./RULES.md) dosyasına bakın.
Uygulama, bu gereksinimleri katmanlı mimari ve üç ayrı yapılandırılmış LLM çağrısıyla
(CriteriaExtractor / CVExtractor / CandidateEvaluator) gerçekleştirir.

AI araçlarıyla geliştirme süreci ve promptlar için [`AI_USAGE.md`](./AI_USAGE.md).

## Bilinen sınırlamalar

- Taranmış (görsel) PDF desteklenmiyor — OCR kapsam dışı, net hata döner.
- Kriter ağırlıklandırma yok, tüm kriterler eşit ağırlıklı.
- Tek Ollama modeli/tek instance — yüksek eşzamanlı yük için tasarlanmadı; 5 CV batch'i
  bir extraction ve bir evaluation çağrısıyla işlenir.
- SQLite tek dosya — çoklu process/yatay ölçekleme için uygun değil (kapsam dışı).
