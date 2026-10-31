"""Log ayarları: hem konsola hem %APPDATA%\\YayinUygulamasi\\logs\\uygulama.log dosyasına yazar."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from core import paths


def kur(seviye=logging.INFO) -> None:
    bicim = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    kok = logging.getLogger()
    kok.setLevel(seviye)
    kok.handlers.clear()

    dosya = RotatingFileHandler(paths.log_klasoru() / "uygulama.log", maxBytes=1_000_000,
                                backupCount=3, encoding="utf-8")
    dosya.setFormatter(bicim)
    kok.addHandler(dosya)

    if sys.stderr is not None:  # pencereli (konsolsuz) exe'de stderr olmayabilir
        konsol = logging.StreamHandler()
        konsol.setFormatter(bicim)
        kok.addHandler(konsol)

    def yakalanmamis(tur, deger, iz):
        logging.getLogger("hata").critical("Yakalanmamış hata", exc_info=(tur, deger, iz))

    sys.excepthook = yakalanmamis
