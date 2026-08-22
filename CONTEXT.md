# Domain Sözlüğü

- **Criterion:** Kullanıcının sohbet içinde dinamik olarak tanımladığı değerlendirme
  ölçütü. Kimliği, etiketi, açıklaması ve CV'de aranabilecek kanıt ipuçlarını taşır.
- **Criterion evidence draft:** Extractor'ın tek bir criterion için önerdiği kısa,
  birebir kaynak alıntısı; backend doğrulamasından önce güvenilir sayılmaz.
- **Verified evidence:** Python'ın kaynak span'ını bulup kararlı ID verdiği ve semantic
  verifier'ın `supports` veya `contradicts` olarak sınıflandırdığı kanıt.
- **Normalized candidate JSON:** Genel CV alanlarıyla her criterion için canonical
  criterion evidence listesini birlikte taşıyan, kaynak doğrulaması tamamlanmış profil.
- **Grounding:** Bir çıkarımın CV kaynağında gerçekten bulunduğunu doğrular; adayın
  kriterle ne kadar uyumlu olduğuna karar vermez.
- **Evaluation:** Yalnız normalized candidate JSON içindeki doğrulanmış evidence ID'lerini
  seçerek puan ve nitel rapor üretir; kanıt metni veya ID üretemez.
