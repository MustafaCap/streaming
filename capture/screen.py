"""Ekran yakalama.

dxcam (DirectX, hızlı) ile başlar; başlatılamazsa veya hata verirse mss'e
(yavaş ama her yerde çalışır) geçer. Kaynak koparsa (ör. monitör çıkarıldı)
uygulama çökmez: grab() None döner ve birkaç saniyede bir yeniden denenir.
"""

import logging
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)


class _DxcamYakalayici:
    ad = "dxcam"

    def __init__(self, monitor: int):
        import dxcam
        self._kamera = dxcam.create(output_idx=monitor, output_color="RGB")
        if self._kamera is None:
            raise RuntimeError("dxcam.create None döndü")
        self._son = None

    def yakala(self):
        kare = self._kamera.grab()
        if kare is not None:  # ekranda değişiklik yoksa dxcam None verir
            self._son = kare
        return self._son

    def kapat(self):
        try:
            self._kamera.release()
        except Exception:
            pass


class _MssYakalayici:
    ad = "mss"

    def __init__(self, monitor: int):
        import mss
        self._sct = mss.mss()
        if monitor + 1 >= len(self._sct.monitors):
            raise RuntimeError(f"{monitor} numaralı monitör yok")
        self._bolge = self._sct.monitors[monitor + 1]  # mss'te 0 = tüm ekranlar birleşik

    def yakala(self):
        kare = np.asarray(self._sct.grab(self._bolge))
        return cv2.cvtColor(kare, cv2.COLOR_BGRA2RGB)

    def kapat(self):
        try:
            self._sct.close()
        except Exception:
            pass


YONTEMLER = {"dxcam": _DxcamYakalayici, "mss": _MssYakalayici}


def monitor_dikdortgeni(monitor: int):
    """Monitörün sanal masaüstündeki (sol, üst, genişlik, yükseklik) değeri; bulunamazsa None."""
    try:
        import mss
        with mss.mss() as sct:
            m = sct.monitors[monitor + 1]
            return m["left"], m["top"], m["width"], m["height"]
    except Exception:
        return None


def fare_konumu():
    """Fare imlecinin ekrandaki konumu (x, y); imleç gizliyse (ör. oyunda) veya Windows değilse None."""
    import sys
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class CURSORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("hCursor", wintypes.HANDLE), ("ptScreenPos", wintypes.POINT)]

    bilgi = CURSORINFO()
    bilgi.cbSize = ctypes.sizeof(CURSORINFO)
    if not ctypes.windll.user32.GetCursorInfo(ctypes.byref(bilgi)):
        return None
    if not bilgi.flags & 0x1:  # CURSOR_SHOWING
        return None
    return bilgi.ptScreenPos.x, bilgi.ptScreenPos.y


class EkranKaynagi:
    """Bir monitörü yakalar. Hata durumunda kendi kendini toparlar."""

    YENIDEN_DENEME_SN = 2.0

    def __init__(self, monitor: int = 0, tercih: str = "dxcam"):
        self.monitor = monitor
        self.tercih = tercih if tercih in YONTEMLER else "dxcam"
        self._yakalayici = None
        self._son_deneme = 0.0
        self.son_hata = ""
        self.dikdortgen = None  # (sol, üst, genişlik, yükseklik)

    @property
    def yontem(self) -> str:
        return self._yakalayici.ad if self._yakalayici else ""

    @property
    def calisiyor(self) -> bool:
        return self._yakalayici is not None

    def _ac(self) -> None:
        sira = [self.tercih] + [y for y in YONTEMLER if y != self.tercih]
        hatalar = []
        for ad in sira:
            try:
                self._yakalayici = YONTEMLER[ad](self.monitor)
                self.dikdortgen = monitor_dikdortgeni(self.monitor)
                log.info("Ekran yakalama başladı: %s, monitör %d %s", ad, self.monitor, self.dikdortgen)
                self.son_hata = ""
                return
            except Exception as e:
                hatalar.append(f"{ad}: {e}")
        self.son_hata = "; ".join(hatalar)
        log.warning("Ekran yakalanamıyor (%s)", self.son_hata)

    def grab(self):
        """RGB numpy dizisi veya kaynak yoksa None döndürür. Asla hata fırlatmaz."""
        if self._yakalayici is None:
            simdi = time.monotonic()
            if simdi - self._son_deneme < self.YENIDEN_DENEME_SN:
                return None
            self._son_deneme = simdi
            self._ac()
            if self._yakalayici is None:
                return None
        try:
            return self._yakalayici.yakala()
        except Exception as e:
            log.warning("Ekran yakalama koptu (%s): %s", self._yakalayici.ad, e)
            self.son_hata = str(e)
            self.kapat()
            return None

    def imlec(self):
        """Fare bu monitördeyse monitöre göre (x, y), değilse None."""
        if self.dikdortgen is None:
            return None
        konum = fare_konumu()
        if konum is None:
            return None
        sol, ust, w, h = self.dikdortgen
        x, y = konum[0] - sol, konum[1] - ust
        if 0 <= x < w and 0 <= y < h:
            return x, y
        return None

    def kapat(self):
        if self._yakalayici is not None:
            self._yakalayici.kapat()
            self._yakalayici = None
