from app.domain.intent import looks_like_criteria_definition


def test_detects_pdf_example_sentence():
    text = "Bana bu CV'yi React tecrübesi, temiz kod yazımı ve uzaktan çalışma uyumuna göre skorla"
    assert looks_like_criteria_definition(text)


def test_detects_degerlendir_variant():
    assert looks_like_criteria_definition("CV'leri React ve remote uyuma göre değerlendir")


def test_plain_chat_is_not_criteria():
    assert not looks_like_criteria_definition("Bugün Ankara'da hava çok sıcak.")
