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

TURLER = ["kalem", "fosforlu", "ok", "kare", "yazi", "lazer", "silgi"]
TUR_ADLARI = {"kalem": "Kalem", "fosforlu": "Fosforlu kalem", "ok": "Ok", "kare": "Kare", "yazi": "Yazı",
              "lazer": "Lazer", "silgi": "Silgi"}
# Çizim renkleri kullanıcının içeriğidir (arayüzün gri kuralına girmez): beyaz, kırmızı, sarı, mavi
RENKLER = ["#F4F4F5", "#EF4444", "#FACC15", "#3B82F6"]
RENK_ADLARI = ["Beyaz", "Kırmızı", "Sarı", "Mavi"]
VARSAYILAN_RENK = 1          # kırmızı
LAZER_RENGI = "#EF4444"      # eski ad (lazer artık seçili rengi kullanır)
KALINLIKLAR = ["ince", "orta", "kalin"]
KALINLIK_ADLARI = {"ince": "İnce", "orta": "Orta", "kalin": "Kalın"}
KALINLIK_CARPANI = {"ince": 0.6, "orta": 1.0, "kalin": 1.8}

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
    carpan: float = 1.0                             # ince / orta / kalın

    @property
    def kalinlik(self) -> float:
        return KALINLIK.get(self.tur, 4 / 1080) * self.carpan


def _parca_uzakligi(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    uz = dx * dx + dy * dy
    t = 0.0 if uz == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / uz))
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def sekle_degiyor_mu(s: Sekil, x: float, y: float, yaricap: float, oran: float = 16 / 9) -> bool:
    """Silgi (x, y) noktasında şekle değiyor mu. oran: monitör en/boy (x'i y ölçeğine çevirir)."""
    def u(a, b):   # yatay mesafe ekranda daha uzun
        return a * oran, b
    px, py = u(x, y)
    pay = yaricap + s.kalinlik / 2
    if s.tur in ("kalem", "fosforlu"):
        pts = [u(*n[:2]) for n in s.noktalar]
        if len(pts) == 1:
            return ((px - pts[0][0]) ** 2 + (py - pts[0][1]) ** 2) ** 0.5 <= pay
        return any(_parca_uzakligi(px, py, *a, *b) <= pay for a, b in zip(pts, pts[1:]))
    if s.tur == "ok":
        a, b = u(*s.noktalar[0]), u(*s.noktalar[1])
        return _parca_uzakligi(px, py, *a, *b) <= pay
    if s.tur == "kare":
        (x0, y0), (x1, y1) = u(*s.noktalar[0]), u(*s.noktalar[1])
        kenarlar = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
        return any(_parca_uzakligi(px, py, *a, *b) <= pay for a, b in kenarlar)
    if s.tur == "yazi":
        x0, y0 = u(*s.noktalar[0])
        w = len(s.metin) * s.kalinlik * 0.55
        h = s.kalinlik * 1.3
        return x0 - yaricap <= px <= x0 + w + yaricap and y0 - yaricap <= py <= y0 + h + yaricap
    return False


class CizimDeposu:
    """Çizimlerin tek kaynağı; arayüz yazar, video hattı okur (iş parçacığı güvenli)."""

    def __init__(self, saat=time.monotonic):
        self._kilit = threading.Lock()
        self._sekiller: list[Sekil] = []
        self._aktif: Sekil | None = None
        self._lazer: list[tuple[float, float, float]] = []
        self.lazer_rengi = RENKLER[VARSAYILAN_RENK]
        self._gecmis: list[tuple] = []   # geri al için: ("ekle", şekil) | ("sil", [(sıra, şekil)])
        self._siliyor: list | None = None
        self._saat = saat
        self.surum = 0  # her değişiklikte artar (katman yeniden çizsin diye)

    # ---- çizim sırasında

    SILGI_YARICAPI = 0.012   # monitör yüksekliğine oranla

    def basla(self, tur: str, renk: str, x: float, y: float, carpan: float = 1.0) -> None:
        with self._kilit:
            if tur == "lazer":
                self.lazer_rengi = renk
                self._lazer.append((x, y, self._saat()))
            elif tur == "silgi":
                self._siliyor = []
                self._sil(x, y)
            else:
                self._aktif = Sekil(tur, renk, [(x, y)] if tur in ("kalem", "fosforlu") else [(x, y), (x, y)],
                                    carpan=carpan)
            self.surum += 1

    def _sil(self, x: float, y: float) -> None:
        """Silgi: değdiği şekilleri bütün olarak kaldırır (kilit içinde çağrılır)."""
        kalan = []
        for i, s in enumerate(self._sekiller):
            if sekle_degiyor_mu(s, x, y, self.SILGI_YARICAPI):
                self._siliyor.append((i, s))
            else:
                kalan.append(s)
        if len(kalan) != len(self._sekiller):
            self._sekiller = kalan

    def surukle(self, x: float, y: float) -> None:
        with self._kilit:
            if self._siliyor is not None:
                self._sil(x, y)
            elif self._aktif is None:
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
            if self._siliyor is not None:
                if self._siliyor:
                    self._gecmis.append(("sil", self._siliyor))
                self._siliyor = None
            s = self._aktif
            self._aktif = None
            if s is not None and self._anlamli(s):
                self._sekiller.append(s)
                self._gecmis.append(("ekle", s))
            self.surum += 1

    def lazer_noktasi(self, x: float, y: float, renk: str | None = None) -> None:
        """Lazer modunda fare basılı olmasa da hareket izi bırakır."""
        with self._kilit:
            if renk:
                self.lazer_rengi = renk
            self._lazer.append((x, y, self._saat()))
            self._lazer = self._lazer[-400:]
            self.surum += 1

    def yazi_ekle(self, renk: str, x: float, y: float, metin: str, carpan: float = 1.0) -> None:
        if metin.strip():
            with self._kilit:
                s = Sekil("yazi", renk, [(x, y)], metin, carpan)
                self._sekiller.append(s)
                self._gecmis.append(("ekle", s))
                self.surum += 1

    @staticmethod
    def _anlamli(s: Sekil) -> bool:
        if s.tur in ("ok", "kare"):
            (x0, y0), (x1, y1) = s.noktalar
            return abs(x1 - x0) + abs(y1 - y0) > 0.005
        return True

    # ---- düzenleme

    def geri_al(self) -> bool:
        """Son çizimi geri alır; son işlem silgiyse silinenleri geri getirir."""
        with self._kilit:
            while self._gecmis:
                tur, veri = self._gecmis.pop()
                if tur == "ekle":
                    if veri in self._sekiller:
                        self._sekiller.remove(veri)
                        self.surum += 1
                        return True
                    continue
                for i, s in sorted(veri, key=lambda p: p[0]):
                    self._sekiller.insert(min(i, len(self._sekiller)), s)
                self.surum += 1
                return True
            if not self._sekiller:
                return False
            self._sekiller.pop()
            self.surum += 1
            return True

    def temizle(self) -> None:
        with self._kilit:
            self._sekiller.clear()
            self._gecmis.clear()
            self._aktif = None
            self._siliyor = None
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
                sekiller[-1] = Sekil(self._aktif.tur, self._aktif.renk, list(self._aktif.noktalar),
                                     carpan=self._aktif.carpan)
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
        renk = hex_rgb(depo.lazer_rengi)
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
