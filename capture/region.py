"""Anlık kare seçme: yumuşak yakınlaştırma ve vurgulama modu.

Seçilen bölge monitöre oranla (0..1) tutulur; böylece çözünürlükten bağımsızdır.
  - yakınlaştırma: çıkışta sadece seçilen kare görünür; tam ekrandan kareye
    animasyonla geçilir (F6 ile geri dönerken de animasyonlu)
  - vurgulama: ekranın tamamı görünür ama seçilen yerin dışı kararır

Bu modül Qt'ye bağlı değildir; video hattı her karede gorunum() ile o anki
durumu sorar. Testlerde saat dışarıdan verilebilir.
"""

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from core import frames

TAM = (0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class Gorunum:
    kirpma: tuple[float, float, float, float]          # monitörün hangi kısmı çıkışa gidiyor (x, y, w, h)
    vurgu: tuple[float, float, float, float] | None    # kararmayan bölge (monitöre oranla) ya da None
    karartma: float                                    # 0 = hiç, 1 = tam karartma gücü


def _yumusat(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _ara(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def normalize(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    """Taşanları kırpar, en az %2 boyut bırakır."""
    x0, y0 = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
    x1, y1 = min(max(x + w, 0.0), 1.0), min(max(y + h, 0.0), 1.0)
    w, h = max(0.02, x1 - x0), max(0.02, y1 - y0)
    x0, y0 = min(x0, 1.0 - w), min(y0, 1.0 - h)
    return x0, y0, w, h


class BolgeSecimi:
    def __init__(self, sure_ms: int = 450, karartma_gucu: float = 0.65, saat=time.monotonic):
        self.sure = max(0.0, sure_ms / 1000.0)
        self.karartma_gucu = karartma_gucu
        self._saat = saat
        self._kilit = threading.Lock()
        self.mod: str | None = None            # None | "yakinlastir" | "vurgula"
        self.bolge: tuple | None = None
        # animasyon: başlangıç ve hedef görünüm
        self._bas = Gorunum(TAM, None, 0.0)
        self._hedef = Gorunum(TAM, None, 0.0)
        self._t0 = -1e9

    @property
    def aktif(self) -> bool:
        return self.mod is not None

    def sec(self, bolge, mod: str = "yakinlastir") -> None:
        bolge = normalize(*bolge)
        if mod == "vurgula":
            hedef = Gorunum(TAM, bolge, 1.0)
        else:
            mod = "yakinlastir"
            hedef = Gorunum(bolge, None, 0.0)
        with self._kilit:
            self._bas = self._su_an()
            self._hedef = hedef
            self._t0 = self._saat()
            self.mod, self.bolge = mod, bolge

    def temizle(self) -> None:
        with self._kilit:
            self._bas = self._su_an()
            # vurgulamadan çıkarken karartma kaybolsun ama bölge çerçevesi kaybolana kadar yerinde kalsın
            self._hedef = Gorunum(TAM, self._bas.vurgu, 0.0)
            self._t0 = self._saat()
            self.mod = None

    def _su_an(self) -> Gorunum:
        if self.sure <= 0:
            return self._hedef
        t = _yumusat((self._saat() - self._t0) / self.sure)
        if t >= 1.0:
            return self._hedef
        b, h = self._bas, self._hedef
        vurgu = h.vurgu or b.vurgu
        if b.vurgu and h.vurgu:
            vurgu = _ara(b.vurgu, h.vurgu, t)
        return Gorunum(_ara(b.kirpma, h.kirpma, t), vurgu, b.karartma + (h.karartma - b.karartma) * t)

    def gorunum(self) -> Gorunum:
        with self._kilit:
            g = self._su_an()
        if g.karartma <= 0.001:
            g = Gorunum(g.kirpma, None, 0.0)
        return g


def uygula(ham: np.ndarray, g: Gorunum, genislik: int, yukseklik: int, karartma_gucu: float = 0.65):
    """Ham monitör karesine görünümü uygular ve çıkış boyutuna sığdırır.

    Döndürür: (kare, donusum) — donusum(x, y) monitör pikselini çıkış pikseline çevirir
    (fare imleci ve çizimler için).
    """
    H, W = ham.shape[:2]
    kx, ky, kw, kh = g.kirpma
    x0, y0 = int(round(kx * W)), int(round(ky * H))
    x1, y1 = max(x0 + 1, int(round((kx + kw) * W))), max(y0 + 1, int(round((ky + kh) * H)))
    parca = ham if (x0, y0, x1, y1) == (0, 0, W, H) else ham[y0:y1, x0:x1]
    olcek, dx, dy = frames.sigdir_donusumu(x1 - x0, y1 - y0, genislik, yukseklik)
    kare = frames.sigdir(parca, genislik, yukseklik)

    def donusum(x, y):
        return (x - x0) * olcek + dx, (y - y0) * olcek + dy

    if g.vurgu is not None and g.karartma > 0:
        vx, vy, vw, vh = g.vurgu
        ax, ay = donusum(vx * W, vy * H)
        bx, by = donusum((vx + vw) * W, (vy + vh) * H)
        ax, ay = max(0, int(ax)), max(0, int(ay))
        bx, by = min(genislik, int(bx)), min(yukseklik, int(by))
        parlak = kare[ay:by, ax:bx].copy() if bx > ax and by > ay else None
        kare = cv2.convertScaleAbs(kare, alpha=1.0 - karartma_gucu * g.karartma)
        if parlak is not None:
            kare[ay:by, ax:bx] = parlak
            renk = (int(76 * g.karartma), int(155 * g.karartma), int(255 * g.karartma))  # vurgu mavisi
            cv2.rectangle(kare, (ax, ay), (bx - 1, by - 1), renk, 2, cv2.LINE_AA)
    return kare, donusum
