"""Kare (görüntü) yardımcıları. Saf numpy/OpenCV, test edilebilir."""

import cv2
import numpy as np


def siyah_kare(genislik: int, yukseklik: int) -> np.ndarray:
    return np.zeros((yukseklik, genislik, 3), np.uint8)


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
