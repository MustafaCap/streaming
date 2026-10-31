"""Kare (görüntü) yardımcıları. Saf numpy/OpenCV, test edilebilir."""

import cv2
import numpy as np


def siyah_kare(genislik: int, yukseklik: int) -> np.ndarray:
    return np.zeros((yukseklik, genislik, 3), np.uint8)


def sigdir_donusumu(w: int, h: int, genislik: int, yukseklik: int) -> tuple[float, int, int]:
    """sigdir()'in kullandığı ölçek ve kaydırma: kaynak (x, y) -> çıkış (x*olcek + dx, y*olcek + dy)."""
    olcek = min(genislik / w, yukseklik / h)
    yeni_w, yeni_h = max(1, round(w * olcek)), max(1, round(h * olcek))
    return olcek, (genislik - yeni_w) // 2, (yukseklik - yeni_h) // 2


# Klasik ok imleci (sol üst ucu 0,0), 1 birim = 1 piksel @ 20 piksel boy
_IMLEC = np.array([[0, 0], [0, 16], [4, 12], [7, 19], [10, 18], [7, 11], [12, 11]], np.float32)


def imlec_ciz(kare: np.ndarray, x: float, y: float, boy: int = 22) -> None:
    """Kareye (yerinde) beyaz dolgulu, siyah kenarlı bir fare oku çizer.

    dxcam ve mss fare imlecini yakalamaz; imleci kendimiz ekliyoruz.
    (Aşama 8'deki imleç vurgulama halkası da buraya eklenecek.)
    """
    noktalar = (_IMLEC * (boy / 19.0) + np.array([x, y], np.float32)).round().astype(np.int32)
    cv2.fillPoly(kare, [noktalar], (255, 255, 255), cv2.LINE_AA)
    cv2.polylines(kare, [noktalar], True, (0, 0, 0), 1, cv2.LINE_AA)


def sigdir(kare: np.ndarray, genislik: int, yukseklik: int) -> np.ndarray:
    """Kareyi en-boy oranını bozmadan hedef boyuta sığdırır, boşluklar siyah kalır.

    Ör. 21:9 monitör 16:9 çıkışta üstte/altta siyah bant ile görünür.
    """
    h, w = kare.shape[:2]
    if (w, h) == (genislik, yukseklik):
        return kare
    olcek = min(genislik / w, yukseklik / h)
    yeni_w, yeni_h = max(1, round(w * olcek)), max(1, round(h * olcek))
    yontem = cv2.INTER_AREA if olcek < 1 else cv2.INTER_LINEAR
    kucuk = cv2.resize(kare, (yeni_w, yeni_h), interpolation=yontem)
    if (yeni_w, yeni_h) == (genislik, yukseklik):
        return kucuk
    tuval = siyah_kare(genislik, yukseklik)
    x, y = (genislik - yeni_w) // 2, (yukseklik - yeni_h) // 2
    tuval[y:y + yeni_h, x:x + yeni_w] = kucuk
    return tuval


_ZEMIN = (18, 20, 25)        # #121419
_IKINCIL_YAZI = (163, 169, 184)  # #A3A9B8
_YAZI_FONTLARI = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
_font_onbellek: dict = {}
_bilgi_onbellek: dict = {}


def _font(boy: int):
    from PIL import ImageFont
    if boy not in _font_onbellek:
        for yol in _YAZI_FONTLARI:
            try:
                _font_onbellek[boy] = ImageFont.truetype(yol, boy)
                break
            except OSError:
                continue
        else:
            _font_onbellek[boy] = ImageFont.load_default(boy)
    return _font_onbellek[boy]


def yazi_yaz(kare: np.ndarray, metin: str, merkez: tuple[int, int], boy: int,
             renk=(232, 234, 240)) -> np.ndarray:
    """Kareye Türkçe karakter destekli yazı yazar (Pillow ile). Yeni dizi döndürür."""
    from PIL import Image, ImageDraw
    resim = Image.fromarray(kare)
    ciz = ImageDraw.Draw(resim)
    satirlar = metin.split("\n")
    font = _font(boy)
    yukseklikler = [ciz.textbbox((0, 0), s or " ", font=font) for s in satirlar]
    toplam = sum(b[3] - b[1] for b in yukseklikler) + (len(satirlar) - 1) * boy // 3
    y = merkez[1] - toplam // 2
    for satir, b in zip(satirlar, yukseklikler):
        w = b[2] - b[0]
        ciz.text((merkez[0] - w // 2 - b[0], y - b[1]), satir, font=font, fill=renk)
        y += (b[3] - b[1]) + boy // 3
    return np.asarray(resim).copy()


def bilgi_karesi(genislik: int, yukseklik: int, metin: str, boy: int | None = None) -> np.ndarray:
    """Koyu zemin üzerinde ortalanmış yazı (kaynak yok, bekleme ekranı vb.). Önbelleklidir; değiştirme."""
    anahtar = (genislik, yukseklik, metin, boy)
    if anahtar not in _bilgi_onbellek:
        if len(_bilgi_onbellek) > 32:
            _bilgi_onbellek.clear()
        kare = np.full((yukseklik, genislik, 3), _ZEMIN, np.uint8)
        kare = yazi_yaz(kare, metin, (genislik // 2, yukseklik // 2),
                        boy or max(12, round(36 * genislik / 1280)), _IKINCIL_YAZI)
        kare.setflags(write=False)  # önbellekteki kare yanlışlıkla bozulmasın
        _bilgi_onbellek[anahtar] = kare
    return _bilgi_onbellek[anahtar]


def karistir(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """a'dan b'ye geçiş: t=0 -> a, t=1 -> b."""
    if t <= 0:
        return a
    if t >= 1:
        return b
    return cv2.addWeighted(a, 1.0 - t, b, t, 0.0)
