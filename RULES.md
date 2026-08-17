# PROJE KURALLARI — Yapay Zeka Destekli Dinamik Telegram İK ve Sohbet Botu

Bu dosya, `Yapay Zeka Projesi Telegram API Mülakat Ödevi.pdf` içindeki gereksinimleri
uygulama ve değerlendirme için tek yerde toplar. PDF asıl ve nihai kaynaktır; bu dosya
PDF ile çelişemez. PDF'de zorunlu tutulmayan teknoloji, limit veya iş akışı tercihleri
proje gereksinimi sayılmaz.

## 1. Projenin amacı

Kullanıcılarla günlük konularda asenkron sohbet edebilen ve konuşma içinde tanımlanan
tamamen dinamik kriterlere göre bir İK uzmanı gibi CV analizi yapabilen gelişmiş bir
Telegram botu geliştirilecektir.

Sistem, arka planda yerel veya uzak bir büyük dil modeli altyapısıyla çalışacaktır.

## 2. Genel sohbet modu (Daily Chat)

- Bot, günlük mesajlara bir dil modeli aracılığıyla mantıklı ve akıcı yanıt vermelidir.
- Sohbet geçmişi backend katmanında güvenli biçimde yönetilmelidir.
- Her yeni mesajda önceki konuşmanın bağlamı korunmalıdır.

## 3. Dinamik kriter tanımlama ve tekli CV analizi

- Sabit kriter mimarisi kullanılmamalıdır.
- Kullanıcı, puanlama kriterlerini konuşma içinde serbest metinle tanımlayabilmelidir.
- Tanımlanan kriterler LLM prompt'una dinamik olarak aktarılmalıdır.
- Kullanıcı tek CV yüklediğinde sistem, aktif dinamik kriterlere göre ayrıntılı nitel
  analiz üretmelidir.
- Tekli CV raporu aşağıdaki bölümleri içermelidir:
  - güçlü yönler (`strengths`)
  - zayıf yönler (`weaknesses`)
  - gelişim tavsiyeleri
- Rapor Telegram üzerinden okunaklı bir Markdown şablonuyla sunulmalıdır.

## 4. PDF doğrulama ve LLM Extraction ile standartlaştırma

- Sistem farklı şablon, tablo ve biçimlerdeki PDF CV'leri kabul edebilmelidir.
- Backend, yüklenen PDF'nin bozuk, şifreli, okunamaz veya geçersiz olup olmadığını
  doğrulamalıdır.
- Geçersiz dosya tespit edildiğinde süreç kesilmelidir.
- Kullanıcıya Telegram üzerinden açık ve anlaşılır bir hata mesajı gönderilmelidir.
- Geçerli PDF'den çıkarılan dağınık metin doğrudan analiz edilmemelidir.
- Ham metin önce LLM Extraction yöntemiyle ortak bir JSON şemasına dönüştürülmelidir.
- Ortak JSON en az aşağıdaki temel bilgileri kapsamalıdır:
  - yetenekler
  - iş deneyimi
  - diller
  - eğitim geçmişi
- Puanlama, ayrıntılı analiz ve filtreleme yalnızca bu standart JSON üzerinden
  yürütülmelidir.

Örnek ortak profil şekli:

```json
{
  "candidateName": "string | null",
  "contact": {
    "email": "string | null",
    "phone": "string | null",
    "location": "string | null"
  },
  "summary": "string | null",
  "skills": ["string"],
  "workExperiences": [
    {
      "company": "string | null",
      "title": "string | null",
      "startDate": "string | null",
      "endDate": "string | null",
      "description": "string | null"
    }
  ],
  "education": [
    {
      "institution": "string | null",
      "degree": "string | null",
      "field": "string | null",
      "graduationDate": "string | null"
    }
  ],
  "languages": [
    {
      "name": "string",
      "level": "string | null"
    }
  ]
}
```

## 5. Çoklu CV skorlama ve filtreleme

- Kullanıcı toplu olarak en fazla 5 mock CV gönderebilmelidir.
- Dosyalar asenkron veya paralel thread'ler üzerinde hızlıca işlenmelidir.
- Bot çoklu dosyalar işlenirken yanıt vermeye devam etmeli ve Telegram akışı
  kilitlenmemelidir.
- Her CV, kullanıcının konuşmada tanımladığı dinamik kriter eşleşmelerine göre
  puanlanmalıdır.
- Her adayın puanlarının aritmetik ortalaması hesaplanmalıdır.
- En yüksek ortalamaya sahip ilk 3 aday yapılandırılmış JSON olarak döndürülmelidir.

Beklenen çoklu gönderim çıktısı:

```json
{
  "status": "success",
  "processedCVCount": 5,
  "userDefinedCriteria": [
    "React tecrübesi",
    "Uzaktan çalışma uyumu",
    "Clean Code"
  ],
  "topCandidates": [
    {
      "rank": 1,
      "candidateName": "Caner Bulut",
      "pdfFileName": "cv_caner_bulut.pdf",
      "dynamicScores": {
        "React tecrübesi": 95,
        "Uzaktan çalışma uyumu": 85,
        "Clean Code": 90
      },
      "averageScore": 90.0,
      "hrEvaluation": "Aday, kullanıcının tanımladığı dinamik kriterlere üst düzey uyum sağlamaktadır."
    }
  ]
}
```

Alan adları ve anlamları korunmalıdır. `topCandidates` en yüksek ortalamaya sahip
adayları sıralı biçimde içermelidir.

## 6. Teknik beklentiler

- Backend nesne yönelimli ve katmanlı mimari prensiplerine uygun olmalıdır.
- Backend dili olarak aşağıdakilerden biri kullanılmalıdır:
  - Java (Spring Boot)
  - Python
  - Go (Golang)
- Telegram API entegrasyonu Long Polling veya Webhook kullanmalıdır.
- Telegram mesajlaşma altyapısı kilitlenmeyen ve asenkron olmalıdır.
- LLM motoru olarak aşağıdakilerden biriyle entegrasyon sağlanmalıdır:
  - Ollama
  - vLLM
  - LM Studio

## 7. Vibe Coding ve ileri seviye AI araçları

- Kodun tamamının geleneksel yöntemlerle elle yazılması beklenmez.
- Cursor, Claude Code, GitHub Copilot, Windsurf, Antigravity, Codex veya benzeri
  yeni nesil AI geliştirme araçlarından etkin biçimde yararlanılmalıdır.
- AI tarafından kod üretilmesi eksi değil, verimlilik göstergesidir.
- Aday mülakat savunmasında aşağıdaki konulara hâkim olmalıdır:
  - kullandığı prompting yaklaşımı
  - üretilen kodun mimarisi
  - LLM Extraction modeli
  - asenkron çalışma yapısı
  - seçilen dilin pratikleri
  - istisna ve hata yönetimi

## 8. Değerlendirme kriterleri

### 8.1 Dinamik Prompt başarısı

- Sohbetten gelen kriterleri prompt'a dinamik olarak gömebilme
- LLM Extraction kurgusunu yönetebilme
- Tekli nitel analiz ve çoklu JSON modlarını kararlı çalıştırabilme

### 8.2 PDF doğrulama ve LLM Extraction kalitesi

- Farklı ve bozuk PDF yapılarını backend'de yakalayabilme
- Dağınık PDF metnini ortak JSON şemasına doğru biçimde çıkarabilme

### 8.3 Asenkron süreç ve bağlam yönetimi

- Telegram akışını kilitlememe
- Çoklu dosyalar işlenirken botun yanıt vermeye devam etmesi
- Sohbet geçmişini ve bağlamı koruma

### 8.4 Vibe Coding hâkimiyeti

- Yeni nesil AI araçlarını etkin kullanma
- Üretilen mimariyi, dil özelliklerini ve istisna yönetimini teknik olarak savunabilme

## 9. Teslim kabul listesi

Durum: uygulandı ve doğrulandı — hem `pytest tests/ -v` (46 passed, mock LLM) hem de
gerçek yerel `qwen2.5:7b` sunucusuna karşı canlı uçtan uca çalıştırma ile (bkz.
`AI_USAGE.md` "Doğrulama"). Canlı koşuda 2 gerçek sorun bulundu ve düzeltildi — ayrıntı
`AI_USAGE.md`'de.

- [x] Günlük sohbet mantıklı ve akıcı çalışıyor. — `chat_service.py`
- [x] Sohbet bağlamı yeni mesajlarda korunuyor. — `sqlite_repo.py` üzerinden kalıcı history
- [x] Kriterler serbest metinden dinamik olarak tanımlanabiliyor. — `criteria_service.py`; canlı
      testte model label'ı küçük eş anlamlı sapmayla döndürdü ("tecrübesi"→"deneyimi"),
      `_grounded_criteria` bunu konu değişmediği için kabul ediyor (bilinçli tasarım, bkz.
      `test_keeps_semantic_label_but_drops_unrelated_extra_criterion`) — bu nedenle garanti
      "birebir kopya" değil, "kullanıcının konusuna sadık" seviyesindedir.
- [x] Tek CV için kriter bazlı Markdown analiz raporu üretiliyor. — `formatter.format_single_analysis`
- [x] Bozuk, şifreli, okunamaz ve geçersiz PDF'ler açık hatayla reddediliyor. — `pymupdf_parser.py`
- [x] PDF metni ortak JSON şemasına LLM Extraction ile dönüştürülüyor. — `CandidateProfile` + `CV_EXTRACTOR_SYSTEM`
- [x] Sonraki analiz ve skorlama yalnızca ortak JSON üzerinden yapılıyor. — evaluator prompt'u yalnız `profile.model_dump_json()` alır, ham metin girmez
- [x] En fazla 5 CV asenkron veya paralel işleniyor. — `batch_analysis_service.py`, `asyncio.gather`.
      "Hızlıca" konusunda dürüst not: canlı ölçümde 5 CV batch adımı tek başına ~580s
      (~9.7 dk) sürdü (qwen2.5:7b, kısıtlı JSON şema üretimi — girdi metni yalnızca ~834
      token, süre CV boyutundan değil şema karmaşıklığından kaynaklanıyor). Kod paralel/
      asenkron çalışıyor, ama tek yerel 7B model + grammar-constrained decoding ile
      "hızlı" gerçek zamanlı bir Telegram deneyimi vermiyor — bkz. README "Bilinen
      sınırlamalar".
- [x] Aritmetik ortalamaya göre ilk 3 aday beklenen JSON sözleşmesiyle dönüyor. — `scoring.compute_average` / `rank_top_n`, `MultiAnalysisResponse(extra="forbid")`
- [x] Bot çoklu analiz sırasında yanıt vermeye devam ediyor. — `concurrent_updates(8)` + chat_id bazlı lock (global lock yok)
- [x] Backend nesne yönelimli ve katmanlı mimariye uyuyor. — domain/application/infrastructure/presentation
- [x] Telegram ve seçilen LLM motoru entegrasyonları çalışıyor. — python-telegram-bot + Ollama (`qwen2.5:7b`)
- [x] Aday, AI destekli geliştirme sürecini ve üretilen kodu teknik olarak savunabiliyor. — bkz. `AI_USAGE.md`
