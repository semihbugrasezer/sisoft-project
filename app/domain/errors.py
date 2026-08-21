"""Uygulama hataları. Her biri kullanıcıya gösterilecek sade Türkçe mesaj taşır."""


class AppError(Exception):
    """Kullanıcıya doğrudan gösterilebilecek mesaj taşıyan taban hata."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class PDFValidationError(AppError):
    pass


class LLMOutputValidationError(AppError):
    def __init__(self, detail: str):
        super().__init__("Model beklenen formatta yanıt üretemedi. Lütfen tekrar deneyin.")
        self.detail = detail


class LLMUnavailableError(AppError):
    def __init__(self, detail: str):
        super().__init__("Model şu anda yanıt vermiyor. Lütfen daha sonra tekrar deneyin.")
        self.detail = detail


class IntentUndecidableError(AppError):
    """Mesajın kriter tanımı mı sohbet mi olduğu belirlenemedi.

    Ayrı bir tip: burada mesajı sessizce "sohbet" saymak, kullanıcının kriter
    tanımını kaybetmek olurdu ve bunu ancak CV gönderdiğinde fark ederdi. Açık
    hata + yönlendirme, sessiz yanlış-moddan iyidir (bkz. CriteriaService)."""

    def __init__(self, detail: str):
        super().__init__(
            "Mesajının değerlendirme kriteri mi yoksa sohbet mi olduğunu belirleyemedim. "
            "Tekrar dener misin? Kriterleri /criteria <kriterler> ile de tanımlayabilirsin."
        )
        self.detail = detail


class NoCriteriaDefinedError(AppError):
    def __init__(self):
        super().__init__(
            "Önce değerlendirme kriteri tanımlamalısınız. Örn:\n"
            "/criteria React tecrübesi, temiz kod yazımı ve uzaktan çalışma uyumu"
        )
