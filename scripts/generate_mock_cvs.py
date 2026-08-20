"""Demo/test için 5 mock CV PDF'i üretir — her biri FARKLI bir belge yapısında.

Ödev PDF §3 "Sisteme beslenecek PDF dosyalarının tamamı farklı şablonlarda, tablo
yapılarında ve biçimlerde olacaktır" diyor. Beşini de aynı şablonla üretmek bu
şartı test etmez; aşağıdaki beş layout kasıtlı olarak birbirinden farklıdır:

    cv_caner_bulut.pdf    tek kolon, klasik akış
    cv_burak_yildiz.pdf   iki kolon (yan yana bölümler)
    cv_mert_demir.pdf     tablo tabanlı (çizgili satırlar)
    cv_elif_kaya.pdf      farklı bölüm sıralaması + madde işaretleri
    cv_zeynep_arslan.pdf  çok sayfalı

Hepsi metin tabanlı (text-based) PDF'dir; OCR gerektirmez. PyMuPDF zaten
bağımlılık — yeni paket eklenmedi.
"""
import pathlib

import pymupdf

# --- İçerik (layout'tan bağımsız) --------------------------------------------
# Aynı aday verisi farklı yapılarda sunulur; böylece "farklı şablon -> aynı
# CandidateProfile" iddiası test edilebilir hale gelir.

CANDIDATES = {
    "cv_caner_bulut.pdf": {
        "layout": "single_column",
        "name": "Caner Bulut",
        "title": "Frontend Developer",
        "contact": "caner.bulut@example.com | Ankara",
        "summary": (
            "5 yildir React ve TypeScript ile kurumsal frontend projeleri gelistiriyorum. "
            "Uzaktan calisma deneyimim var, dagitik ekiplerde 3 yildir remote calisiyorum."
        ),
        "experience": [
            ("Frontend Developer, TechCo (2021-2025)",
             "React, Redux, Next.js ile e-ticaret platformu gelistirdim. Clean code "
             "prensiplerine bagli kaldim, code review sureclerini yonettim. Ekip tamamen "
             "remote calisiyordu."),
            ("Junior Developer, WebStudio (2019-2021)",
             "jQuery tabanli projelerden React'e gecis yaptim."),
        ],
        "education": [("Bilgisayar Muhendisligi, ODTU", "2015-2019")],
        "skills": ["React", "TypeScript", "Redux", "Next.js", "Jest", "Git", "Clean Code", "SOLID"],
        "languages": [("Turkce", "anadil"), ("Ingilizce", "ileri")],
    },
    "cv_burak_yildiz.pdf": {
        "layout": "two_column",
        "name": "Burak Yildiz",
        "title": "Senior Frontend Engineer",
        "contact": "burak.yildiz@example.com | Antalya",
        "summary": (
            "8 yillik React uzmanlik deneyimim var, acik kaynak katkilarim mevcut. "
            "Tamamen dagitik (remote-first) sirketlerde calistim."
        ),
        "experience": [
            ("Senior Frontend Engineer, CloudNet (2019-2025)",
             "Buyuk olcekli React uygulamalarinda mimari kararlar aldim. Clean code, "
             "code review kulturu ve test-driven development uyguladim. Sirket remote-first."),
            ("Frontend Engineer, MediaCorp (2016-2019)",
             "React ve Redux ile haber platformu gelistirdim."),
        ],
        "education": [("Bilgisayar Muhendisligi, Istanbul Teknik Universitesi", "2012-2016")],
        "skills": ["React", "Redux", "TypeScript", "GraphQL", "Clean Code", "TDD", "Webpack"],
        "languages": [("Turkce", "anadil"), ("Ingilizce", "ileri"), ("Fransizca", "orta")],
    },
    "cv_mert_demir.pdf": {
        "layout": "table",
        "name": "Mert Demir",
        "title": "Full Stack Developer",
        "contact": "mert.demir@example.com | Izmir",
        "summary": (
            "React ve Node.js agirlikli full-stack gelistirici. Kod kalitesine onem veririm, "
            "her PR icin unit test yazarim. Freelance olarak 2 yildir tamamen remote calisiyorum."
        ),
        "experience": [
            ("Full Stack Developer, Freelance (2023-2025)",
             "Birden fazla musteri icin React + Node.js projeleri teslim ettim, tamami remote. "
             "Clean code ve test coverage konusunda titizim."),
            ("Full Stack Developer, AppWorks (2021-2023)",
             "React ve Express ile SaaS urunu gelistirdim."),
        ],
        "education": [("Bilgisayar Muhendisligi, Ege Universitesi", "2017-2021")],
        "skills": ["React", "Node.js", "Express", "TypeScript", "Jest", "Clean Code", "CI/CD"],
        "languages": [("Turkce", "anadil"), ("Ingilizce", "ileri"), ("Almanca", "baslangic")],
    },
    "cv_elif_kaya.pdf": {
        "layout": "reordered_sections",
        "name": "Elif Kaya",
        "title": "Backend Developer",
        "contact": "elif.kaya@example.com | Istanbul",
        "summary": (
            "Python ve Go ile backend sistemler gelistiren bir yazilim muhendisiyim. "
            "React deneyimim sinirli, birkac kucuk dashboard projesinde kullandim."
        ),
        "experience": [
            ("Backend Developer, DataFlow (2020-2025)",
             "Go ile mikroservisler gelistirdim, PostgreSQL ve Redis kullandim. "
             "Ofisten calistim, uzaktan calisma deneyimim yok."),
            ("Stajyer, StartupX (2019-2020)", "Python ile veri isleme scriptleri yazdim."),
        ],
        "education": [("Yazilim Muhendisligi, Bogazici Universitesi", "2015-2019")],
        "skills": ["Python", "Go", "PostgreSQL", "Docker", "Kubernetes"],
        "languages": [("Turkce", "anadil"), ("Ingilizce", "orta")],
    },
    "cv_zeynep_arslan.pdf": {
        "layout": "multipage",
        "name": "Zeynep Arslan",
        "title": "UI/UX Designer",
        "contact": "zeynep.arslan@example.com | Bursa",
        "summary": (
            "Kullanici arayuzu tasarimi konusunda uzmanim, kodlama deneyimim sinirlidir."
        ),
        "experience": [
            ("UI/UX Designer, DesignHub (2020-2025)",
             "Figma ile mobil ve web arayuzleri tasarladim. Ofis ortaminda calistim."),
            ("Junior Designer, PixelWorks (2018-2020)",
             "Kurumsal kimlik ve landing page tasarimlari yaptim."),
        ],
        "education": [("Grafik Tasarim, Marmara Universitesi", "2016-2020")],
        "skills": ["Figma", "Adobe XD", "Sketch", "Prototyping"],
        "languages": [("Turkce", "anadil"), ("Ingilizce", "orta")],
    },
}


def _header(page, data, y=60):
    page.insert_text((50, y), data["name"], fontsize=16)
    page.insert_text((50, y + 20), data["title"], fontsize=11)
    page.insert_text((50, y + 36), data["contact"], fontsize=9)
    return y + 60


def _single_column(doc, data):
    page = doc.new_page()
    y = _header(page, data)
    body = [("Ozet", data["summary"])]
    body.append(("Is Deneyimi", "\n".join(f"{t}\n{d}" for t, d in data["experience"])))
    body.append(("Egitim", "\n".join(f"{s} ({p})" for s, p in data["education"])))
    body.append(("Yetenekler", ", ".join(data["skills"])))
    body.append(("Diller", ", ".join(f"{n} ({lv})" for n, lv in data["languages"])))
    for title, content in body:
        page.insert_text((50, y), title, fontsize=12)
        y += 16
        rect = pymupdf.Rect(50, y, 545, y + 130)
        page.insert_textbox(rect, content, fontsize=9)
        y += 130


def _two_column(doc, data):
    """Yan yana iki kolon — metin çıkarma sırası bu layout'ta zorlanır."""
    page = doc.new_page()
    y = _header(page, data)
    left = pymupdf.Rect(40, y, 290, 780)
    right = pymupdf.Rect(305, y, 555, 780)
    page.insert_textbox(left, "OZET\n" + data["summary"] + "\n\nYETENEKLER\n"
                        + "\n".join(f"- {s}" for s in data["skills"]), fontsize=9)
    right_text = "IS DENEYIMI\n" + "\n\n".join(f"{t}\n{d}" for t, d in data["experience"])
    right_text += "\n\nEGITIM\n" + "\n".join(f"{s} ({p})" for s, p in data["education"])
    right_text += "\n\nDILLER\n" + "\n".join(f"{n}: {lv}" for n, lv in data["languages"])
    page.insert_textbox(right, right_text, fontsize=9)


def _table(doc, data):
    """Çizgili tablo satırları — etiket/değer sütunları."""
    page = doc.new_page()
    y = _header(page, data)
    rows = [
        ("Ozet", data["summary"]),
        ("Deneyim", " | ".join(f"{t}: {d}" for t, d in data["experience"])),
        ("Egitim", "; ".join(f"{s} ({p})" for s, p in data["education"])),
        ("Yetenekler", ", ".join(data["skills"])),
        ("Diller", ", ".join(f"{n} ({lv})" for n, lv in data["languages"])),
    ]
    for label, value in rows:
        height = 90
        page.draw_rect(pymupdf.Rect(45, y, 550, y + height))
        page.draw_line(pymupdf.Point(150, y), pymupdf.Point(150, y + height))
        page.insert_textbox(pymupdf.Rect(50, y + 4, 145, y + height), label, fontsize=9)
        page.insert_textbox(pymupdf.Rect(155, y + 4, 545, y + height), value, fontsize=8)
        y += height


def _reordered_sections(doc, data):
    """Bölüm sırası farklı: önce yetenekler ve eğitim, en sonda özet."""
    page = doc.new_page()
    y = _header(page, data)
    body = [
        ("YETENEKLER", "\n".join(f"* {s}" for s in data["skills"])),
        ("EGITIM", "\n".join(f"* {s} ({p})" for s, p in data["education"])),
        ("DILLER", "\n".join(f"* {n} - {lv}" for n, lv in data["languages"])),
        ("IS DENEYIMI", "\n".join(f"* {t}\n  {d}" for t, d in data["experience"])),
        ("HAKKIMDA", data["summary"]),
    ]
    for title, content in body:
        page.insert_text((50, y), title, fontsize=11)
        y += 14
        page.insert_textbox(pymupdf.Rect(50, y, 545, y + 120), content, fontsize=9)
        y += 120


def _multipage(doc, data):
    """İçerik iki sayfaya bölünür — parser tüm sayfaları okumalı."""
    first = doc.new_page()
    y = _header(first, data)
    first.insert_text((50, y), "Ozet", fontsize=12)
    first.insert_textbox(pymupdf.Rect(50, y + 16, 545, y + 120), data["summary"], fontsize=9)
    first.insert_text((50, y + 140), "Is Deneyimi", fontsize=12)
    first.insert_textbox(
        pymupdf.Rect(50, y + 156, 545, y + 400),
        "\n\n".join(f"{t}\n{d}" for t, d in data["experience"]), fontsize=9,
    )

    second = doc.new_page()
    second.insert_text((50, 60), f"{data['name']} — devam", fontsize=11)
    rest = "Egitim\n" + "\n".join(f"{s} ({p})" for s, p in data["education"])
    rest += "\n\nYetenekler\n" + ", ".join(data["skills"])
    rest += "\n\nDiller\n" + ", ".join(f"{n} ({lv})" for n, lv in data["languages"])
    second.insert_textbox(pymupdf.Rect(50, 90, 545, 500), rest, fontsize=9)


LAYOUTS = {
    "single_column": _single_column,
    "two_column": _two_column,
    "table": _table,
    "reordered_sections": _reordered_sections,
    "multipage": _multipage,
}


def main():
    out_dir = pathlib.Path(__file__).parent.parent / "mock_cvs"
    out_dir.mkdir(exist_ok=True)
    for filename, data in CANDIDATES.items():
        doc = pymupdf.open()
        LAYOUTS[data["layout"]](doc, data)
        doc.save(out_dir / filename)
        doc.close()
        print(f"yazildi: {out_dir / filename}  [{data['layout']}]")


if __name__ == "__main__":
    main()
