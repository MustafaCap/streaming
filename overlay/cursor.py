"""İmleç vurgulama: imlecin etrafında yumuşak bir halka, tıklayınca genişleyen dalga.

Sadece çıkış görüntüsüne çizilir (karşı taraf görür). Tıklamalar Windows'tan
GetAsyncKeyState ile okunur; video hattı her karede bir kez sorar.
"""

import sys
import time

import cv2
import numpy as np

DALGA_SURESI = 0.5


def sol_tus_basili() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)


class ImlecVurgusu:
    def __init__(self, renk=(255, 212, 59), saat=time.monotonic, tus_okuyucu=sol_tus_basili):
        self.renk = renk          # sarı (#FFD43B)
        self._saat = saat
        self._tus = tus_okuyucu
        self._onceki_basili = False
        self._dalgalar: list[tuple[float, float, float]] = []  # (x, y, başlangıç) monitör pikseli

    def guncelle(self, konum) -> None:
        """Her karede çağrılır: yeni tıklama varsa dalga başlatır. konum: monitör pikseli ya da None."""
        basili = self._tus()
        if basili and not self._onceki_basili and konum is not None:
            self._dalgalar.append((konum[0], konum[1], self._saat()))
        self._onceki_basili = basili
        simdi = self._saat()
        self._dalgalar = [d for d in self._dalgalar if simdi - d[2] < DALGA_SURESI][-5:]

    def ciz(self, kare: np.ndarray, konum_cikis, donusum, olcek: float) -> None:
        """Kareye (yerinde) halka ve dalgaları çizer. konum_cikis: imlecin çıkış karesindeki yeri."""
        simdi = self._saat()
        r = max(10, int(26 * olcek))
        if konum_cikis is not None:
            x, y = int(konum_cikis[0]), int(konum_cikis[1])
            katman = kare.copy()
            cv2.circle(katman, (x, y), r, self.renk, -1, cv2.LINE_AA)
            cv2.addWeighted(katman, 0.25, kare, 0.75, 0, dst=kare)
            cv2.circle(kare, (x, y), r, self.renk, max(1, int(2 * olcek)), cv2.LINE_AA)
        for dx, dy, t0 in self._dalgalar:
            t = (simdi - t0) / DALGA_SURESI
            if not 0 <= t < 1:
                continue
            cx, cy = donusum(dx, dy)
            yaricap = int(r * (0.6 + 1.6 * t))
            kalin = max(1, int(4 * olcek * (1 - t)))
            renk = tuple(int(c * (1 - t) + 255 * t * 0.0) for c in self.renk)
            cv2.circle(kare, (int(cx), int(cy)), yaricap, renk, kalin, cv2.LINE_AA)
