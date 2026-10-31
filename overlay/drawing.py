"""Çizim kalemi: çizimlerin kendisi (veri) ve çıkış görüntüsüne çizilmesi.

Çizimler monitöre oranla (0..1) saklanır. Aynı çizim iki yerde gösterilir:
  1) ekrandaki şeffaf katmanda (sen görürsün; bu katman ekran yakalamaya girmez)
  2) video hattında, çıkış karesinin üstüne (karşı taraf görür)
İkincisi sayesinde tam ekran oyunlarda katman görünmese bile çizim yayına gider
(brifteki 13. özellik), ve F6 ile yakınlaştırınca çizimler de doğru yerde kalır.

Bu modül Qt'ye bağlı değildir; testlerde doğrudan kullanılır.
"""

import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

TURLER = ["kalem", "fosforlu", "ok", "kare", "yazi", "lazer"]
TUR_ADLARI = {"kalem": "Kalem", "fosforlu": "Fosforlu", "ok": "Ok", "kare": "Kare", "yazi": "Yazı",
              "lazer": "Lazer"}
RENKLER = ["#FF8A3D", "#FFD43B", "#4C9BFF", "#FFFFFF"]   # turuncu (varsayılan), sarı, mavi, beyaz
LAZER_RENGI = "#FF3B3B"

# Kalınlıklar monitör yüksekliğine oranla (1080p'de piksel / 1080)
KALINLIK = {"kalem": 4 / 1080, "fosforlu": 22 / 1080, "ok": 5 / 1080, "kare": 4 / 1080,
            "yazi": 34 / 1080, "lazer": 7 / 1080}
LAZER_OMRU = 1.6      # lazer izinin her noktası bu kadar saniyede kaybolur
FOSFOR_SAYDAMLIK = 0.4


def hex_rgb(renk: str) -> tuple[int, int, int]:
    renk = renk.lstrip("#")
    return int(renk[0:2], 16), int(renk[2:4], 16), int(renk[4:6], 16)


@dataclass
class Sekil:
    tur: str
    renk: str
    noktalar: list = field(default_factory=list)   # [(x, y)] monitöre oranla; lazerde (x, y, zaman)
    metin: str = ""

    @property
    def kalinlik(self) -> float:
        return KALINLIK.get(self.tur, 4 / 1080)


class CizimDeposu:
    """Çizimlerin tek kaynağı; arayüz yazar, video hattı okur (iş parçacığı güvenli)."""

    def __init__(self, saat=time.monotonic):
        self._kilit = threading.Lock()
        self._sekiller: list[Sekil] = []
        self._aktif: Sekil | None = None
        self._lazer: list[tuple[float, float, float]] = []
        self._saat = saat
        self.surum = 0  # her değişiklikte artar (katman yeniden çizsin diye)

    # ---- çizim sırasında

    def basla(self, tur: str, renk: str, x: float, y: float) -> None:
        with self._kilit:
            if tur == "lazer":
                self._lazer.append((x, y, self._saat()))
            else:
                self._aktif = Sekil(tur, renk, [(x, y)] if tur in ("kalem", "fosforlu") else [(x, y), (x, y)])
            self.surum += 1

    def surukle(self, x: float, y: float) -> None:
        with self._kilit:
            if self._aktif is None:
                self._lazer.append((x, y, self._saat()))
                self._lazer = self._lazer[-400:]
            elif self._aktif.tur in ("kalem", "fosforlu"):
                son = self._aktif.noktalar[-1]
                if abs(son[0] - x) + abs(son[1] - y) > 0.0008:  # çok yakın noktaları atla
                    self._aktif.noktalar.append((x, y))
            else:
                self._aktif.noktalar[-1] = (x, y)
            self.surum += 1

    def bitir(self) -> None:
        with self._kilit:
            s = self._aktif
            self._aktif = None
            if s is not None and self._anlamli(s):
                self._sekiller.append(s)
            self.surum += 1

    def lazer_noktasi(self, x: float, y: float) -> None:
        """Lazer modunda fare basılı olmasa da hareket izi bırakır."""
        with self._kilit:
            self._lazer.append((x, y, self._saat()))
            self._lazer = self._lazer[-400:]
            self.surum += 1

    def yazi_ekle(self, renk: str, x: float, y: float, metin: str) -> None:
        if metin.strip():
            with self._kilit:
                self._sekiller.append(Sekil("yazi", renk, [(x, y)], metin))
                self.surum += 1

    @staticmethod
    def _anlamli(s: Sekil) -> bool:
        if s.tur in ("ok", "kare"):
            (x0, y0), (x1, y1) = s.noktalar
            return abs(x1 - x0) + abs(y1 - y0) > 0.005
        return True

    # ---- düzenleme

    def geri_al(self) -> bool:
        with self._kilit:
            if not self._sekiller:
                return False
            self._sekiller.pop()
            self.surum += 1
            return True

    def temizle(self) -> None:
        with self._kilit:
            self._sekiller.clear()
            self._aktif = None
            self._lazer.clear()
            self.surum += 1

    # ---- okuma

    def anlik(self) -> tuple[list[Sekil], list[tuple[float, float, float]]]:
        """(şekiller, lazer izi [(x, y, yaş 0..1)]) — eski lazer noktaları atılır."""
        simdi = self._saat()
        with self._kilit:
            self._lazer = [p for p in self._lazer if simdi - p[2] < LAZER_OMRU]
            sekiller = list(self._sekiller) + ([self._aktif] if self._aktif is not None else [])
            if self._aktif is not None:
                sekiller[-1] = Sekil(self._aktif.tur, self._aktif.renk, list(self._aktif.noktalar))
            lazer = [(x, y, (simdi - t) / LAZER_OMRU) for x, y, t in self._lazer]
        return sekiller, lazer

    @property
    def bos(self) -> bool:
        with self._kilit:
            return not self._sekiller and self._aktif is None and not self._lazer


# ------------------------------------------------------------------ çıkış karesine çizim

def _yazi(kare: np.ndarray, metin: str, x: int, y: int, boy: int, renk) -> np.ndarray:
    from PIL import Image, ImageDraw

    from core.frames import _font
    resim = Image.fromarray(kare)
    ciz = ImageDraw.Draw(resim)
    font = _font(max(8, boy))
    # okunabilirlik için ince koyu kenar
    ciz.text((x, y), metin, font=font, fill=renk, stroke_width=max(1, boy // 14), stroke_fill=(0, 0, 0))
    return np.asarray(resim).copy()


def cizimleri_uygula(kare: np.ndarray, depo: CizimDeposu, monitor_w: int, monitor_h: int, donusum):
    """Çizimleri çıkış karesine ekler. donusum(x_px, y_px) monitör pikselini çıkış pikseline çevirir.

    Çizim yoksa kareyi olduğu gibi döndürür (kopyalamaz).
    """
    sekiller, lazer = depo.anlik()
    if not sekiller and not lazer:
        return kare
    kare = kare.copy()
    x0, y0 = donusum(0, 0)
    olcek = donusum(1, 0)[0] - x0  # monitör pikseli başına çıkış pikseli

    def nokta(p):
        x, y = donusum(p[0] * monitor_w, p[1] * monitor_h)
        return int(round(x)), int(round(y))

    for s in sekiller:
        kalin = max(1, int(round(s.kalinlik * monitor_h * olcek)))
        renk = hex_rgb(s.renk)
        if s.tur == "kalem":
            pts = np.array([nokta(p) for p in s.noktalar], np.int32)
            if len(pts) == 1:
                cv2.circle(kare, tuple(pts[0]), max(1, kalin // 2), renk, -1, cv2.LINE_AA)
            else:
                cv2.polylines(kare, [pts], False, renk, kalin, cv2.LINE_AA)
        elif s.tur == "fosforlu":
            pts = np.array([nokta(p) for p in s.noktalar], np.int32)
            katman = kare.copy()
            if len(pts) == 1:
                cv2.circle(katman, tuple(pts[0]), kalin // 2, renk, -1)
            else:
                cv2.polylines(katman, [pts], False, renk, kalin, cv2.LINE_8)
            cv2.addWeighted(katman, FOSFOR_SAYDAMLIK, kare, 1 - FOSFOR_SAYDAMLIK, 0, dst=kare)
        elif s.tur == "ok":
            a, b = nokta(s.noktalar[0]), nokta(s.noktalar[1])
            uzunluk = max(1.0, float(np.hypot(b[0] - a[0], b[1] - a[1])))
            uc = min(0.4, (kalin * 5) / uzunluk)
            cv2.arrowedLine(kare, a, b, renk, kalin, cv2.LINE_AA, tipLength=uc)
        elif s.tur == "kare":
            a, b = nokta(s.noktalar[0]), nokta(s.noktalar[1])
            cv2.rectangle(kare, a, b, renk, kalin, cv2.LINE_AA)
        elif s.tur == "yazi":
            x, y = nokta(s.noktalar[0])
            kare = _yazi(kare, s.metin, x, y, max(8, int(round(s.kalinlik * monitor_h * olcek))), renk)

    if lazer:
        renk = hex_rgb(LAZER_RENGI)
        kalin = max(2, int(round(KALINLIK["lazer"] * monitor_h * olcek)))
        for i in range(1, len(lazer)):
            a, b = lazer[i - 1], lazer[i]
            canlilik = 1.0 - b[2]
            if canlilik <= 0:
                continue
            k = max(1, int(kalin * canlilik))
            # kaybolurken rengi zemine karıştırmak pahalı; kalınlık azalarak iz kaybolur
            cv2.line(kare, nokta(a), nokta(b), renk, k, cv2.LINE_AA)
        bas = lazer[-1]
        if bas[2] < 0.3:
            cv2.circle(kare, nokta(bas), kalin + 3, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(kare, nokta(bas), kalin + 1, renk, -1, cv2.LINE_AA)
    return kare
