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


def bilgi_karesi(genislik: int, yukseklik: int, metin: str) -> np.ndarray:
    """Kaynak yokken gönderilecek koyu ekran. (OpenCV yazısı Türkçe karakter desteklemez, ASCII kullan.)"""
    kare = np.full((yukseklik, genislik, 3), (25, 20, 18), np.uint8)  # RGB: #121419'a yakın
    olcek = genislik / 1280
    (tw, th), _ = cv2.getTextSize(metin, cv2.FONT_HERSHEY_SIMPLEX, 1.2 * olcek, 2)
    cv2.putText(kare, metin, ((genislik - tw) // 2, (yukseklik + th) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2 * olcek, (163, 169, 184), 2, cv2.LINE_AA)
    return kare
