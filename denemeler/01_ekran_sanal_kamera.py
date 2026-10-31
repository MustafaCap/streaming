"""Deneme 1: Ekranı yakala ve sanal kameraya gönder.

Ne deniyoruz?
  - dxcam ekranı hızlı yakalayabiliyor mu? (Olmazsa mss'e geçeriz.)
  - pyvirtualcam, OBS Virtual Camera sürücüsü üzerinden görüntüyü
    Zoom/Meet/Discord'a gönderebiliyor mu?
  - 1280x720, 30 FPS'de işlemci ne kadar yoruluyor?

Çalıştırma:
  python 01_ekran_sanal_kamera.py            # dxcam ile
  python 01_ekran_sanal_kamera.py --mss      # mss ile (yedek yöntem)
  python 01_ekran_sanal_kamera.py --monitor 1  # ikinci monitör

Durdurmak için: Ctrl+C
"""

import sys
import argparse
import time

import cv2
import numpy as np
import pyvirtualcam

GENISLIK, YUKSEKLIK, FPS = 1280, 720, 30


def dxcam_yakalayici(monitor: int):
    import dxcam

    kamera = dxcam.create(output_idx=monitor, output_color="RGB")
    if kamera is None:
        raise RuntimeError("dxcam başlatılamadı")
    son_kare = None

    def yakala():
        nonlocal son_kare
        kare = kamera.grab()
        # dxcam, ekranda değişiklik yoksa None döner; o zaman son kareyi kullan.
        if kare is not None:
            son_kare = kare
        return son_kare

    return yakala


def mss_yakalayici(monitor: int):
    import mss

    sct = mss.mss()
    bolge = sct.monitors[monitor + 1]  # mss'te 0 = tüm ekranlar birleşik

    def yakala():
        kare = np.asarray(sct.grab(bolge))  # BGRA
        return cv2.cvtColor(kare, cv2.COLOR_BGRA2RGB)

    return yakala


def main():
    # Türkçe karakterler her konsolda/yönlendirmede düzgün çıksın
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mss", action="store_true", help="dxcam yerine mss kullan")
    ap.add_argument("--monitor", type=int, default=0)
    args = ap.parse_args()

    yontem = "mss" if args.mss else "dxcam"
    try:
        yakala = mss_yakalayici(args.monitor) if args.mss else dxcam_yakalayici(args.monitor)
    except Exception as e:
        print(f"[HATA] {yontem} başlatılamadı: {e}")
        print("İpucu: --mss ile tekrar dene.")
        return

    siyah_sayaci = 0
    with pyvirtualcam.Camera(width=GENISLIK, height=YUKSEKLIK, fps=FPS) as cam:
        print(f"Sanal kamera açıldı: {cam.device} ({yontem})")
        print("Şimdi Zoom/Meet/Discord'da kamera olarak 'OBS Virtual Camera' seç.")
        print("Durdurmak için Ctrl+C.\n")

        kare_sayisi, sure_toplam, son_rapor = 0, 0.0, time.time()
        try:
            while True:
                t0 = time.perf_counter()
                kare = yakala()
                if kare is None:
                    kare = np.zeros((YUKSEKLIK, GENISLIK, 3), np.uint8)
                else:
                    kare = cv2.resize(kare, (GENISLIK, YUKSEKLIK), interpolation=cv2.INTER_AREA)

                # Siyah ekran kontrolü (iki ekran kartlı laptoplarda olabiliyor)
                if kare.max() < 5:
                    siyah_sayaci += 1
                else:
                    siyah_sayaci = 0

                cam.send(kare)
                sure_toplam += time.perf_counter() - t0
                kare_sayisi += 1
                cam.sleep_until_next_frame()

                if time.time() - son_rapor >= 2:
                    ort_ms = 1000 * sure_toplam / kare_sayisi
                    print(f"FPS: {kare_sayisi / (time.time() - son_rapor):5.1f}  |  "
                          f"kare başına iş: {ort_ms:5.1f} ms")
                    if siyah_sayaci > FPS * 2:
                        print("  [UYARI] Görüntü 2 saniyedir tamamen siyah! "
                              "README'deki 'Siyah ekran' bölümüne bak.")
                    kare_sayisi, sure_toplam, son_rapor = 0, 0.0, time.time()
        except KeyboardInterrupt:
            print("\nDurduruldu.")


if __name__ == "__main__":
    main()
