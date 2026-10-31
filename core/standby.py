"""Bekleme ekranı videosu: kısa bir videoyu (MP4, WEBM, AVI, MOV, GIF) sessiz ve döngüde oynatır.

Video hattı her karede kare() ister; video kendi hızında ilerler (çıkış 30 FPS,
video 24 FPS olsa da doğru hızda oynar). Biterse başa sarar. Açılamazsa None
döner ve bekleme ekranı yazıya düşer (uygulama çökmez).

Ses çalınmaz; bekleme ekranında ses kapalıdır.
"""

import logging
import shutil
import time
from pathlib import Path

import numpy as np

from core import frames, paths

log = logging.getLogger(__name__)

VIDEO_UZANTILARI = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".gif", ".wmv", ".m4v"}


def video_mu(yol: str) -> bool:
    return bool(yol) and Path(yol).suffix.lower() in VIDEO_UZANTILARI


def uygulamaya_kopyala(kaynak: str) -> str:
    """Seçilen dosyayı %APPDATA%\\RizeOn\\bekleme\\ içine kopyalar.

    Neden: OpenCV'nin video açıcısı Windows'ta Türkçe karakterli yolları (ör. "Masaüstü")
    açamıyor; ayrıca kullanıcı dosyayı silse/taşısa da bekleme ekranı bozulmaz.
    """
    hedef_klasor = paths.veri_klasoru() / "bekleme"
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    if Path(kaynak).resolve().parent == hedef_klasor.resolve():
        return str(kaynak)   # zaten kopyalanmış
    # her seçimde yeni ad: video hattı eski dosyayı açık tutuyor olabilir, yenisini ayrı açar
    hedef = hedef_klasor / f"bekleme_{int(time.time())}{Path(kaynak).suffix.lower()}"
    for eski in hedef_klasor.glob("bekleme_*"):
        try:
            eski.unlink()
        except OSError:
            pass
    shutil.copyfile(kaynak, hedef)
    return str(hedef)


class BeklemeVideosu:
    def __init__(self, saat=time.monotonic):
        self._saat = saat
        self._yol = None
        self._cap = None
        self._fps = 30.0
        self._t0 = 0.0
        self._okunan = 0          # baştan beri okunan kare sayısı (bu döngüde)
        self._son: np.ndarray | None = None
        self._boyut = (0, 0)
        self.hata = ""

    def _ac(self, yol: str) -> bool:
        import cv2
        self.kapat()
        self._yol = yol
        cap = cv2.VideoCapture(yol)
        if not cap.isOpened():
            self.hata = f"Video açılamadı: {yol}"
            log.warning(self.hata)
            cap.release()
            return False
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        self._fps = fps if 1 <= fps <= 120 else 30.0
        self._cap, self._t0, self._okunan, self.hata = cap, self._saat(), 0, ""
        return True

    def _sonraki(self, w: int, h: int):
        ok, bgr = self._cap.read()
        if not ok:   # bitti: başa sar
            import cv2
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, bgr = self._cap.read()
            self._t0, self._okunan = self._saat(), 0
            if not ok:
                return None
        import cv2
        self._okunan += 1
        kare = frames.sigdir(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), w, h)
        kare = np.ascontiguousarray(kare)
        kare.setflags(write=False)
        return kare

    def kare(self, yol: str, w: int, h: int) -> np.ndarray | None:
        if yol != self._yol:
            if not self._ac(yol):
                return None
            self._son = None
        if self._cap is None:
            return None
        if self._boyut != (w, h):
            self._boyut, self._son = (w, h), None
        istenen = int((self._saat() - self._t0) * self._fps) + 1   # şu ana kadar gösterilmesi gereken kare
        adim = 0
        while (self._son is None or self._okunan < istenen) and adim < 4:   # geride kalırsa en fazla 4 kare atla
            yeni = self._sonraki(w, h)
            if yeni is None:
                self.hata = "Video okunamadı"
                return self._son
            self._son = yeni
            adim += 1
        if self._okunan < istenen - 4:   # çok geride: saati kareye eşitle (yavaş bilgisayar)
            self._t0 = self._saat() - self._okunan / self._fps
        return self._son

    def kapat(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap, self._yol, self._son = None, None, None
