# Katkı Rehberi

## Geliştirme Ortamı

```bash
git clone https://github.com/semihbugrasezer/sisoft-project.git
cd sisoft-project

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # pytest, ruff, mypy dahil

cp .env.example .env                  # TELEGRAM_BOT_TOKEN ekleyin
```

Gerçek token/API anahtarı değerlerini **asla commit etmeyin**.

## Branch ve PR Politikası

`main` korunan branch'tir: CI kontrolleri geçmeden ve bir onay alınmadan
merge edilemez. Kalıcı bir `development` branch **kullanılmaz** — tek
geliştiricili bir projede ikinci bir entegrasyon noktası karşılıksız yüktür.

Her değişiklik kısa ömürlü bir branch'te geliştirilir:

```text
feat/      yeni davranış
fix/       hata düzeltmesi
docs/      dokümantasyon
test/      test değişikliği
chore/     tooling / repository bakımı
refactor/  davranışı değiştirmeyen düzenleme
```

Akış:

```bash
git switch main
git pull --ff-only origin main
git switch -c fix/example

# değişiklik + test

git push -u origin fix/example
gh pr create --base main
gh pr merge --auto --squash   # onay + CI tamamlanınca otomatik merge olur
```

Merge yöntemi **yalnızca squash**'tır (repository ayarında zorunlu kılınmıştır)
ve merge sonrası branch otomatik silinir. Böylece `main` geçmişi her PR için
tek ve anlamlı bir commit içerir.

## Kalite Kontrolleri

PR açmadan önce hepsini çalıştırın — CI de aynılarını çalıştırır:

```bash
ruff check app main.py tests scripts
mypy app main.py
python -m pytest tests/ -q
python -m pip check
```

## Test Beklentisi

Davranış değiştiren her PR bir test içermelidir. Şu alanlarda test zorunlu
kabul edilir:

- PDF doğrulama ve metin çıkarma
- LLM yapılandırılmış çıktı sözleşmeleri (şema, validator)
- Skorlama ve sıralama mantığı
- Asenkron/eşzamanlılık davranışı
- SQLite veri yaşam döngüsü
- Telegram çıktı ve hata yönetimi

Test verisi olarak **gerçek CV veya gerçek Telegram token'ı kullanılmaz**;
mock CV üretimi için `scripts/generate_mock_cvs.py` ve
`scripts/generate_invalid_cvs.py` vardır.

Ayrıntı: [docs/TESTING.md](docs/TESTING.md).

## LLM ve Prompt Değişiklikleri

Prompt değişiklikleri "daha iyi göründüğü" gerekçesiyle kabul edilmez. PR
açıklaması şunları belirtmelidir:

- hangi somut hata veya davranış hedeflendi,
- nasıl doğrulandı (test ve/veya canlı koşu),
- çıktı şeması/sözleşmesi değişiyor mu,
- farklı model veya backend'de farklı davranış bekleniyor mu.

CV ve kullanıcı içeriği daima **güvenilmeyen veri** kabul edilir; bkz.
[SECURITY.md](SECURITY.md).

## Commit Mesajları

Kısa, açıklayıcı, emir kipinde. Bir commit tek mantıksal değişiklik içermeli:

```text
feat: kriter etiketlerinde birebir eşleşme zorunlu kıl
fix: analiz hata verse de bekleyen CV'leri temizle
docs: eşzamanlılık modelini belgele
test: PDF kırpma sınırını kapsa
```
