"""Sanal kamera çıkışı.

OBS Studio'nun kurduğu "OBS Virtual Camera" sürücüsüne görüntüyü kendi
kodumuzla (outputs/obs_kamera.py) gönderir. Zoom/Meet/Discord'da kamera olarak
"OBS Virtual Camera" seçilir. Başka bir sürücüye geçmek istenirse sadece bu
dosyanın değişmesi yeterli.
"""

import logging
import threading

log = logging.getLogger(__name__)


class SanalKameraYok(RuntimeError):
    """Sürücü kurulu değil (OBS kurulmamış veya sanal kamera hiç başlatılmamış) ya da başka program kullanıyor."""


class SanalKameraCikisi:
    def __init__(self, genislik: int, yukseklik: int, fps: int):
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self._kamera = None
        self._kilit = threading.Lock()   # kapatılırken aynı anda kare yazılmasın (bellek bırakılıyor)

    @property
    def acik(self) -> bool:
        return self._kamera is not None

    @property
    def cihaz_adi(self) -> str:
        from outputs.obs_kamera import CIHAZ_ADI
        return CIHAZ_ADI if self._kamera else ""

    def ac(self) -> None:
        from outputs.obs_kamera import KameraAcilamadi, ObsSanalKamera
        with self._kilit:
            if self._kamera is not None:
                return
            try:
                self._kamera = ObsSanalKamera(self.genislik, self.yukseklik, self.fps)
            except KameraAcilamadi as e:
                raise SanalKameraYok(str(e)) from e
        log.info("Sanal kamera açıldı: %s (%dx%d, %d fps)", self.cihaz_adi, self.genislik, self.yukseklik, self.fps)

    def gonder(self, kare_rgb) -> None:
        with self._kilit:
            if self._kamera is not None:
                self._kamera.gonder(kare_rgb)

    def kapat(self) -> None:
        with self._kilit:
            kamera, self._kamera = self._kamera, None
            if kamera is None:
                return
            try:
                kamera.kapat()
            except Exception:
                log.exception("Sanal kamera kapatılırken hata")
        log.info("Sanal kamera kapatıldı")
