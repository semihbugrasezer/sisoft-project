"""PDF doğrulamasının reddetmesi gereken bozuk/geçersiz dosyaları üretir — canlı
Telegram testinde her validation adımını (bkz. pymupdf_parser.py) tetiklemek için."""
import pathlib

import pymupdf


def main():
    out_dir = pathlib.Path(__file__).parent.parent / "mock_cvs" / "invalid"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Hiç PDF değil — imza kontrolüne takılır ("Dosya geçerli bir PDF değil.")
    (out_dir / "cv_gecersiz_uzanti.pdf").write_bytes(b"Bu bir PDF degil, duz metin dosyasi.")

    # 2. %PDF- imzası var ama gövde bozuk — fitz.open() patlar ("PDF açılamadı, dosya bozuk olabilir.")
    (out_dir / "cv_bozuk.pdf").write_bytes(b"%PDF-1.4\n" + b"\x00\xff\xde\xad\xbe\xef" * 50)

    # 3. Şifreli PDF — is_encrypted=True ("PDF şifreli; lütfen şifresiz bir kopya yükleyin.")
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "Gizli CV Icerigi")
    doc.save(out_dir / "cv_sifreli.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234")
    doc.close()

    # 4. Geçerli sayfa ama metin yok (taranmış/görsel belge simülasyonu) —
    #    ("PDF açıldı ama okunabilir metin bulunamadı — taranmış (görsel) belge olabilir.")
    doc = pymupdf.open()
    doc.new_page()  # boş sayfa, metin eklenmedi
    doc.save(out_dir / "cv_taranmis_bos.pdf")
    doc.close()

    for f in sorted(out_dir.iterdir()):
        print(f"yazildi: {f}")


if __name__ == "__main__":
    main()
