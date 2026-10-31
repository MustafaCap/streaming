"""Sanal kamera çıkışı.

Şimdilik pyvirtualcam üzerinden OBS Virtual Camera sürücüsünü kullanır.
Aşama 0 planındaki gibi bu bir sınıfın arkasında; ileride başka bir sürücüye
(ör. Unity Capture veya Windows 11'in kendi sanal kamera API'si) geçmek için
sadece bu dosyayı değiştirmek yeterli olacak.
"""

import logging

log = logging.getLogger(__name__)


class SanalKameraYok(RuntimeError):
    """Sürücü kurulu değil (OBS kurulmamış veya sanal kamera hiç başlatılmamış)."""


class SanalKameraCikisi:
    def __init__(self, genislik: int, yukseklik: int, fps: int):
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self._kamera = None

    @property
    def acik(self) -> bool:
        return self._kamera is not None

    @property
    def cihaz_adi(self) -> str:
        return self._kamera.device if self._kamera else ""

    def ac(self) -> None:
        import pyvirtualcam
        try:
            self._kamera = pyvirtualcam.Camera(width=self.genislik, height=self.yukseklik,
                                               fps=self.fps, backend="obs")
        except RuntimeError as e:
            raise SanalKameraYok(str(e)) from e
        log.info("Sanal kamera açıldı: %s", self._kamera.device)

    def gonder(self, kare_rgb) -> None:
        if self._kamera is not None:
            self._kamera.send(kare_rgb)

    def kapat(self) -> None:
        if self._kamera is not None:
            try:
                self._kamera.close()
            except Exception:
                log.exception("Sanal kamera kapatılırken hata")
            self._kamera = None
            log.info("Sanal kamera kapatıldı")
