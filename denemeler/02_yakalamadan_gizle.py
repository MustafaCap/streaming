"""Deneme 2: Kendi penceremizi ekran yakalamadan gizle.

Ne deniyoruz?
  Windows 10 2004+ / Windows 11'deki SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
  ile bir pencere ekranda görünür ama ekran yakalamaya (dxcam, mss, Zoom ekran
  paylaşımı) girmez. Kalem araç çubuğu, bildirimler, kare seçme katmanı ve
  önizleme penceresi için buna ihtiyacımız var.

Çalıştırma:
  python 02_yakalamadan_gizle.py

Script kendi kendini test eder:
  1) Pembe bir pencere açar, ekranı yakalar -> pencere görüntüde OLMALI.
  2) Gizlemeyi açar, tekrar yakalar -> pencere görüntüde OLMAMALI.
Sonucu konsola yazar. Pencere açık kalır; istersen 01 numaralı denemeyi de
çalıştırıp Zoom önizlemesinde pembe pencerenin görünmediğine bakabilirsin.
"""

import ctypes
import sys
from ctypes import wintypes

import mss
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel

WDA_NONE = 0x00
WDA_EXCLUDEFROMCAPTURE = 0x11

user32 = ctypes.windll.user32
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]


def pencere_dikdortgeni(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"left": r.left, "top": r.top, "width": r.right - r.left, "height": r.bottom - r.top}


def pembe_orani(hwnd) -> float:
    """Pencerenin bulunduğu bölgeyi yakalar, pembe piksel oranını döndürür."""
    with mss.mss() as sct:
        img = np.asarray(sct.grab(pencere_dikdortgeni(hwnd)))  # BGRA
    b, g, r = img[..., 0].astype(int), img[..., 1].astype(int), img[..., 2].astype(int)
    pembe = (r > 200) & (g < 60) & (b > 200)
    return float(pembe.mean())


def main():
    app = QApplication(sys.argv)
    w = QLabel("Bu pencere ekranda görünüyor.\nAma yakalamada görünmemeli.")
    w.setAlignment(Qt.AlignCenter)
    w.setStyleSheet("background:#FF00FF; color:white; font-size:22px; font-weight:bold;")
    w.setWindowFlag(Qt.WindowStaysOnTopHint)
    w.resize(500, 300)
    w.move(200, 200)
    w.show()
    hwnd = int(w.winId())

    def adim1():
        oran = pembe_orani(hwnd)
        print(f"1) Gizleme KAPALI -> yakalanan görüntüde pembe oranı: %{oran * 100:.0f}")
        ok = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        if not ok:
            print(f"[HATA] SetWindowDisplayAffinity başarısız (hata kodu {ctypes.GetLastError()}).")
            return
        QTimer.singleShot(1000, adim2)

    def adim2():
        oran = pembe_orani(hwnd)
        print(f"2) Gizleme AÇIK   -> yakalanan görüntüde pembe oranı: %{oran * 100:.0f}")
        if oran < 0.05:
            print("\nSONUÇ: BAŞARILI. Pencere ekranda var ama yakalamaya girmiyor.")
        else:
            print("\nSONUÇ: BAŞARISIZ. Pencere hâlâ yakalanıyor. Windows sürümünü (winver) not et.")
        print("Pencereyi kapatarak çıkabilirsin.")

    QTimer.singleShot(1000, adim1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
