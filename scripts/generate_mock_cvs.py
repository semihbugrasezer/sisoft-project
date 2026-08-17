"""Demo/test için 5 basit mock CV PDF'i üretir. PyMuPDF zaten bağımlılık — yeni paket eklenmedi."""
import pymupdf

MOCK_CVS = {
    "cv_caner_bulut.pdf": """Caner Bulut
Frontend Developer
email: caner.bulut@example.com | Ankara

Ozet:
5 yildir React ve TypeScript ile kurumsal frontend projeleri gelistiriyorum.
Uzaktan calisma deneyimim var, dagitik ekiplerde 3 yildir remote calisiyorum.

Is Deneyimi:
- Frontend Developer, TechCo (2021-2025)
  React, Redux, Next.js kullanarak e-ticaret platformu gelistirdim.
  Clean code prensiplerine bagli kaldim, code review surecilerini yonettim.
  Ekip tamamen remote calisiyordu, Slack ve Notion ile koordinasyon sagladim.
- Junior Developer, WebStudio (2019-2021)
  jQuery tabanli projelerden React'e gecis yaptim.

Egitim:
- Bilgisayar Muhendisligi, ODTU (2015-2019)

Yetenekler: React, TypeScript, Redux, Next.js, Jest, Git, Clean Code, SOLID
Diller: Turkce (anadil), Ingilizce (ileri)
""",
    "cv_elif_kaya.pdf": """Elif Kaya
Backend Developer
email: elif.kaya@example.com | Istanbul

Ozet:
Python ve Go ile backend sistemler gelistiren bir yazilim muhendisiyim.
React deneyimim sinirli, birkac kucuk dashboard projesinde kullandim.

Is Deneyimi:
- Backend Developer, DataFlow (2020-2025)
  Go ile mikroservisler gelistirdim, PostgreSQL ve Redis kullandim.
  Ofisten calistim, uzaktan calisma deneyimim yok.
- Stajyer, StartupX (2019-2020)

Egitim:
- Yazilim Muhendisligi, Bogazici Universitesi (2015-2019)

Yetenekler: Python, Go, PostgreSQL, Docker, Kubernetes
Diller: Turkce (anadil), Ingilizce (orta)
""",
    "cv_mert_demir.pdf": """Mert Demir
Full Stack Developer
email: mert.demir@example.com | Izmir

Ozet:
React ve Node.js agirlikli full-stack gelistirici. Kod kalitesine onem veririm,
her PR icin unit test yazarim. Freelance olarak 2 yildir tamamen remote calisiyorum.

Is Deneyimi:
- Full Stack Developer, Freelance (2023-2025)
  Birden fazla musteri icin React + Node.js projeleri teslim ettim, tamami remote.
  Clean code ve test coverage konusunda titizim, ESLint/Prettier standartlari uyguladim.
- Full Stack Developer, AppWorks (2021-2023)
  React ve Express ile SaaS urunu gelistirdim.

Egitim:
- Bilgisayar Muhendisligi, Ege Universitesi (2017-2021)

Yetenekler: React, Node.js, Express, TypeScript, Jest, Clean Code, CI/CD
Diller: Turkce (anadil), Ingilizce (ileri), Almanca (baslangic)
""",
    "cv_zeynep_arslan.pdf": """Zeynep Arslan
UI/UX Designer
email: zeynep.arslan@example.com | Bursa

Ozet:
Kullanici arayuzu tasarimi konusunda uzmanim, kodlama deneyimim sinirlidir.

Is Deneyimi:
- UI/UX Designer, DesignHub (2020-2025)
  Figma ile mobil ve web arayuzleri tasarladim.
  Ofis ortaminda calistim.

Egitim:
- Grafik Tasarim, Marmara Universitesi (2016-2020)

Yetenekler: Figma, Adobe XD, Sketch, Prototyping
Diller: Turkce (anadil), Ingilizce (orta)
""",
    "cv_burak_yildiz.pdf": """Burak Yildiz
Senior Frontend Engineer
email: burak.yildiz@example.com | Antalya

Ozet:
8 yillik React uzmanlik deneyimim var, acik kaynak katkilarim mevcut.
Tamamen dagitik (remote-first) sirketlerde calistim, zaman yonetimim guclu.

Is Deneyimi:
- Senior Frontend Engineer, CloudNet (2019-2025)
  Buyuk olcekli React uygulamalarinda mimari kararlar aldim.
  Clean code, code review kulturu ve test-driven development uyguladim.
  Sirket remote-first, tamamen dagitik ekiple calistim.
- Frontend Engineer, MediaCorp (2016-2019)
  React ve Redux ile haber platformu gelistirdim.

Egitim:
- Bilgisayar Muhendisligi, Istanbul Teknik Universitesi (2012-2016)

Yetenekler: React, Redux, TypeScript, GraphQL, Clean Code, TDD, Webpack
Diller: Turkce (anadil), Ingilizce (ileri), Fransizca (orta)
""",
}


def main():
    import pathlib

    out_dir = pathlib.Path(__file__).parent.parent / "mock_cvs"
    out_dir.mkdir(exist_ok=True)
    for filename, content in MOCK_CVS.items():
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 792), content, fontsize=10)
        doc.save(out_dir / filename)
        doc.close()
        print(f"yazildi: {out_dir / filename}")


if __name__ == "__main__":
    main()
