"""Sahneler ve sahne geçişleri.

Bir sahne, çıkış karesinin nasıl kurulacağını söyler:
  - ekran: ekran görüntüsü arka planda mı
  - kamera: "corner" (köşede küçük), "full" (tam ekran) ya da yok
  - standby: bekleme ekranı (yazı)

Sahneler settings.json'daki "scenes" listesinden okunur, sabit kodlu değildir.
Sahne değişince 0,3 sn'lik yumuşak geçiş (fade) yapılır: son çıkış karesinin
fotoğrafı alınır ve yeni sahneye doğru karıştırılır.

Bu modül Qt'ye bağlı değildir; testlerde doğrudan kullanılır.
"""

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from core import frames

VARSAYILAN_SAHNELER = [
    {"name": "Ekran + Kamera", "screen": True, "camera": "corner"},
    {"name": "Sadece ekran", "screen": True},
    {"name": "Sadece kamera", "camera": "full"},
    {"name": "Bekleme", "standby": True},
]


@dataclass(frozen=True)
class Sahne:
    ad: str
    ekran: bool = False
    kamera: str | None = None   # "corner" | "full" | None
    bekleme: bool = False

    @classmethod
    def sozlukten(cls, s: dict) -> "Sahne":
        kamera = s.get("camera")
        if kamera not in ("corner", "full"):
            kamera = None
        return cls(ad=str(s.get("name", "Sahne")), ekran=bool(s.get("screen", False)),
                   kamera=kamera, bekleme=bool(s.get("standby", False)))


def sahneleri_oku(liste) -> list[Sahne]:
    """Ayarlardaki listeyi okur; boş/bozuksa varsayılan sahneleri döndürür."""
    try:
        sahneler = [Sahne.sozlukten(s) for s in liste if isinstance(s, dict)]
    except Exception:
        sahneler = []
    return sahneler or [Sahne.sozlukten(s) for s in VARSAYILAN_SAHNELER]


@dataclass
class KameraYerlesimi:
    kose: str = "bottom-right"   # top-left | top-right | bottom-left | bottom-right
    boyut: float = 0.25          # çıkış genişliğine oranı
    bosluk: int = 24             # kenardan uzaklık (piksel)
    konum: tuple[float, float] | None = None   # önizlemede sürüklenince: kutunun merkezi (0..1)

    @classmethod
    def ayarlardan(cls, d: dict) -> "KameraYerlesimi":
        kose = d.get("corner", "bottom-right")
        if kose not in ("top-left", "top-right", "bottom-left", "bottom-right"):
            kose = "bottom-right"
        boyut = min(0.6, max(0.1, float(d.get("size", 0.25))))
        konum = d.get("position")
        try:
            konum = (min(1.0, max(0.0, float(konum[0]))), min(1.0, max(0.0, float(konum[1])))) if konum else None
        except (TypeError, ValueError, IndexError):
            konum = None
        return cls(kose=kose, boyut=boyut, bosluk=max(0, int(d.get("margin", 24))), konum=konum)

    def dikdortgen(self, genislik: int, yukseklik: int, oran: float = 16 / 9) -> tuple[int, int, int, int]:
        """Kamera kutusunun (x, y, w, h) yeri; her zaman çıkışın içinde kalır."""
        w = max(16, round(genislik * self.boyut))
        h = max(9, round(w / oran))
        if self.konum is not None:
            x = round(self.konum[0] * genislik - w / 2)
            y = round(self.konum[1] * yukseklik - h / 2)
        else:
            x = self.bosluk if "left" in self.kose else genislik - w - self.bosluk
            y = self.bosluk if "top" in self.kose else yukseklik - h - self.bosluk
        x = min(max(0, x), max(0, genislik - w))
        y = min(max(0, y), max(0, yukseklik - h))
        return x, y, w, h


def _kirp_doldur(kare: np.ndarray, w: int, h: int) -> np.ndarray:
    """Kareyi w x h alanı tam dolduracak şekilde ortadan kırpar ve ölçekler."""
    kh, kw = kare.shape[:2]
    olcek = max(w / kw, h / kh)
    kes_w, kes_h = min(kw, round(w / olcek)), min(kh, round(h / olcek))
    x0, y0 = (kw - kes_w) // 2, (kh - kes_h) // 2
    parca = kare[y0:y0 + kes_h, x0:x0 + kes_w]
    yontem = cv2.INTER_AREA if olcek < 1 else cv2.INTER_LINEAR
    return cv2.resize(parca, (w, h), interpolation=yontem)


_KENAR = (42, 47, 58)  # #2A2F3A


def kamera_kutusu_ciz(tuval: np.ndarray, kamera, yer: KameraYerlesimi) -> None:
    """Tuvalin köşesine kamera görüntüsünü (yoksa 'Kamera yok' kutusunu) yerinde çizer."""
    H, W = tuval.shape[:2]
    x, y, w, h = yer.dikdortgen(W, H)
    if kamera is not None:
        tuval[y:y + h, x:x + w] = _kirp_doldur(kamera, w, h)
    else:
        tuval[y:y + h, x:x + w] = frames.bilgi_karesi(w, h, "Kamera yok", boy=max(12, h // 7))
    cv2.rectangle(tuval, (x - 1, y - 1), (x + w, y + h), _KENAR, 2)


def sahne_karesi(sahne: Sahne, genislik: int, yukseklik: int, ekran, kamera,
                 kamera_acik: bool, yer: KameraYerlesimi, bekleme_metni: str, bekleme=None) -> np.ndarray:
    """Sahneye göre yeni (yazılabilir) bir çıkış karesi kurar.

    ekran: zaten çıkış boyutuna sığdırılmış ekran karesi ya da None (kaynak yok).
    kamera: kameranın son karesi ya da None (kamera yok/kapalı).
    kamera_acik: kullanıcı kamerayı açık mı tuttu (F10).
    bekleme: bekleme ekranını veren fonksiyon (yazı ya da görsel); yoksa düz yazı.
    """
    def bekleme_karesi():
        if bekleme is not None:
            return bekleme().copy()
        return frames.bilgi_karesi(genislik, yukseklik, bekleme_metni).copy()

    if sahne.bekleme:
        return bekleme_karesi()

    if sahne.kamera == "full":
        if not kamera_acik:
            return bekleme_karesi()  # kamera kapalıyken siyah yerine bekleme ekranı
        if kamera is None:
            return frames.bilgi_karesi(genislik, yukseklik, "Kamera bağlı değil").copy()
        return _kirp_doldur(kamera, genislik, yukseklik)

    if sahne.ekran:
        tuval = ekran.copy() if ekran is not None else \
            frames.bilgi_karesi(genislik, yukseklik, "Ekran yakalanamıyor").copy()
    else:
        tuval = frames.siyah_kare(genislik, yukseklik)

    if sahne.kamera == "corner" and kamera_acik:
        kamera_kutusu_ciz(tuval, kamera, yer)
    return tuval


class SahneYoneticisi:
    """Hangi sahnenin aktif olduğunu ve süren geçişi tutar (iş parçacığı güvenli)."""

    def __init__(self, sahneler: list[Sahne], gecis_ms: int = 300, saat=time.monotonic):
        if not sahneler:
            raise ValueError("En az bir sahne gerekli")
        self.sahneler = sahneler
        self.gecis_sn = max(0, gecis_ms) / 1000.0
        self._saat = saat
        self._indeks = 0
        self._kilit = threading.Lock()
        self._gecis_baslangic: float | None = None
        self._gecis_istegi = False
        self._onceki_kare: np.ndarray | None = None

    @property
    def indeks(self) -> int:
        return self._indeks

    @property
    def aktif(self) -> Sahne:
        return self.sahneler[self._indeks]

    def sec(self, indeks: int) -> bool:
        """Sahneyi değiştirir (0 tabanlı). Geçersiz numarada False döner."""
        if not 0 <= indeks < len(self.sahneler):
            return False
        with self._kilit:
            if indeks == self._indeks:
                return True
            self._indeks = indeks
            self._gecis_istegi = self.gecis_sn > 0
        return True

    def gecis_uygula(self, yeni: np.ndarray, son_cikis: np.ndarray | None) -> np.ndarray:
        """Video iş parçacığında her karede çağrılır: geçiş sürüyorsa iki kareyi karıştırır.

        son_cikis: bir önceki karede çıkışa giden kare (geçişin başlangıç fotoğrafı).
        """
        with self._kilit:
            if self._gecis_istegi:
                self._gecis_istegi = False
                if son_cikis is not None and son_cikis.shape == yeni.shape:
                    self._onceki_kare = son_cikis
                    self._gecis_baslangic = self._saat()
            if self._gecis_baslangic is None:
                return yeni
            t = (self._saat() - self._gecis_baslangic) / self.gecis_sn
            onceki = self._onceki_kare
            if t >= 1 or onceki is None:
                self._gecis_baslangic, self._onceki_kare = None, None
                return yeni
        t = t * t * (3 - 2 * t)  # yumuşak başla, yumuşak bitir
        return frames.karistir(onceki, yeni, t)

    @property
    def geciste(self) -> bool:
        return self._gecis_baslangic is not None or self._gecis_istegi
