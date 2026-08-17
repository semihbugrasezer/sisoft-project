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

## Çıktı formatı

**Tekli CV** (Markdown, `formatter.format_single_analysis`): kriter bazlı skorlar,
*Güçlü Yönler*, *Zayıf Yönler*, *Gelişim Tavsiyeleri*, tek cümlelik genel değerlendirme.

**Çoklu CV (top-3)**: alan adları PDF'teki şemayla (sayfa 2) birebir. Aşağıdaki örnek,
mock veri değil — gerçek yerel `qwen2.5:7b` sunucusuna karşı 5 mock CV ile canlı
çalıştırılıp yakalanmış ham çıktının ilk iki adayıdır:

```json
{
  "status": "success",
  "processedCVCount": 5,
  "userDefinedCriteria": ["React deneyimi", "Temiz kod yazımı", "Uzaktan çalışma uyumu"],
  "topCandidates": [
    {
      "rank": 1,
      "candidateName": "Burak Yildiz",
      "pdfFileName": "cv_burak_yildiz.pdf",
      "dynamicScores": {"React deneyimi": 95, "Temiz kod yazımı": 90, "Uzaktan çalışma uyumu": 85},
      "averageScore": 90.0,
      "hrEvaluation": "Burak Yildiz, a seasoned React developer with strong clean code practices and significant remote work experience."
    },
    {
      "rank": 2,
      "candidateName": "Mert Demir",
      "pdfFileName": "cv_mert_demir.pdf",
      "dynamicScores": {"React deneyimi": 80, "Temiz kod yazımı": 90, "Uzaktan çalışma uyumu": 95},
      "averageScore": 88.33,
      "hrEvaluation": "Mert Demir, a full-stack developer with strong React and Node.js skills, excels in clean code practices and remote work."
    }
  ]
}
```

Şema (alan adları, sıralama mantığı) PDF ile birebir uyuyor — `MultiAnalysisResponse`
Pydantic modeli `extra="forbid"` ile buna kilitli, fazladan alan eklenirse validation
hatası fırlatır (`app/domain/models.py`). `hrEvaluation`'ın İngilizce dönmesi bu koşuda
yakalanan bir bug'dı (Türkçe sohbet botu için beklenmiyor); `prompts.py`'ye açık
"çıktı Türkçe olsun" talimatı eklendi ama düzeltme sonrası tam batch koşusu henüz
tekrar çalıştırılıp doğrulanmadı — bkz. `AI_USAGE.md` "Canlı uçtan uca koşu".

## Gereksinimler ve mimari

PDF ile birebir proje gereksinimleri için [`RULES.md`](./RULES.md) dosyasına bakın.
Uygulama, bu gereksinimleri katmanlı mimari ve birbirinden ayrılmış LLM
sorumluluklarıyla (kriter niyeti/extraction, CV extraction ve değerlendirme) gerçekleştirir.

AI araçlarıyla geliştirme süreci ve promptlar için [`AI_USAGE.md`](./AI_USAGE.md).

## Bilinen sınırlamalar

- Taranmış (görsel) PDF desteklenmiyor — OCR kapsam dışı, net hata döner.
- Kriter ağırlıklandırma yok, tüm kriterler eşit ağırlıklı.
- Tek Ollama modeli/tek instance — yüksek eşzamanlı yük için tasarlanmadı; 5 CV batch'i
  bir extraction ve bir evaluation çağrısıyla işlenir. Canlı ölçümde (qwen2.5:7b, Apple
  Silicon GPU) bu iki çağrı ~9-10 dk sürdü — darboğaz kısıtlı JSON şema üretimi, CV
  metin boyutu değil; bkz. `AI_USAGE.md` "Canlı uçtan uca koşu".
- SQLite tek dosya — çoklu process/yatay ölçekleme için uygun değil (kapsam dışı).
