"""Log ayarları: hem konsola hem %APPDATA%\\YayinUygulamasi\\logs\\uygulama.log dosyasına yazar.

Pencereli exe'de konsol yok; bu yüzden hiçbir hata kaybolmasın diye:
  - ana iş parçacığındaki yakalanmamış hatalar (sys.excepthook),
  - arka plan iş parçacıklarındaki yakalanmamış hatalar (threading.excepthook),
  - yerel (C seviyesinde) çökmeler (faulthandler -> logs\\cokme.log)
log'a yazılır. Saniyede onlarca kez tekrarlanan aynı hata log'u doldurmasın diye
SeyrekHata kullanılır: ilk seferinde ayrıntısıyla, sonra arada bir özetle yazılır.
"""

import faulthandler
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from core import paths

_cokme_dosyasi = None   # faulthandler'ın yazdığı dosya açık kalmalı


def kur(seviye=logging.INFO) -> None:
    global _cokme_dosyasi
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

    def is_parcacigi_hatasi(bilgi):
        if bilgi.exc_type is SystemExit:
            return
        ad = bilgi.thread.name if bilgi.thread is not None else "?"
        logging.getLogger("hata").critical("Arka plan iş parçacığında yakalanmamış hata (%s)", ad,
                                           exc_info=(bilgi.exc_type, bilgi.exc_value, bilgi.exc_traceback))

    sys.excepthook = yakalanmamis
    threading.excepthook = is_parcacigi_hatasi

    try:
        if _cokme_dosyasi is None:
            _cokme_dosyasi = open(paths.log_klasoru() / "cokme.log", "a", encoding="utf-8")
            _cokme_dosyasi.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} uygulama başladı\n")
            _cokme_dosyasi.flush()
        faulthandler.enable(file=_cokme_dosyasi, all_threads=True)
    except Exception:
        logging.getLogger(__name__).warning("Çökme kaydı açılamadı", exc_info=True)


class SeyrekHata:
    """Aynı hatayı her seferinde değil, ilk seferinde ayrıntılı, sonra en fazla `aralik_sn`'de bir özetle yazar."""

    def __init__(self, log: logging.Logger, aralik_sn: float = 30.0):
        self.log, self.aralik_sn = log, aralik_sn
        self._son: dict[str, tuple[float, int]] = {}

    def yaz(self, mesaj: str, hata: BaseException | None = None) -> None:
        hata = hata if hata is not None else sys.exc_info()[1]
        anahtar = f"{mesaj}|{type(hata).__name__}|{hata}"
        simdi = time.monotonic()
        son = self._son.get(anahtar)
        if son is None:
            if len(self._son) > 200:
                self._son.clear()
            self._son[anahtar] = (simdi, 0)
            self.log.error(mesaj, exc_info=hata)
            return
        zaman, tekrar = son
        if simdi - zaman >= self.aralik_sn:
            self.log.error("%s (aynı hata son %.0f sn'de %d kez daha oldu): %s", mesaj, simdi - zaman,
                           tekrar + 1, hata)
            self._son[anahtar] = (simdi, 0)
        else:
            self._son[anahtar] = (zaman, tekrar + 1)
