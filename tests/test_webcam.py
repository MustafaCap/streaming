"""Webcam: hata olsa da, hızlı aç/kapa yapılsa da cihaz bırakılmalı (kameranın ışığı açık kalmasın)."""

import threading
import time

import numpy as np

from capture import webcam
from capture.webcam import WebcamKaynagi


class SahteKamera:
    acik_olanlar: list["SahteKamera"] = []
    acilis_suresi = 0.0
    hata_ver = threading.Event()

    def __init__(self, *_):
        time.sleep(SahteKamera.acilis_suresi)
        self.bagli = True
        SahteKamera.acik_olanlar.append(self)

    def isOpened(self):
        return True

    def set(self, *_):
        return True

    def read(self):
        time.sleep(0.01)
        if SahteKamera.hata_ver.is_set():
            SahteKamera.hata_ver.clear()
            raise RuntimeError("sürücü hatası")
        return True, np.zeros((4, 4, 3), np.uint8)

    def release(self):
        if self.bagli:
            self.bagli = False
            SahteKamera.acik_olanlar.remove(self)


def _bekle(kosul, sure=3.0):
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        if kosul():
            return True
        time.sleep(0.02)
    return kosul()


def _hazirla(monkeypatch):
    SahteKamera.acik_olanlar = []
    SahteKamera.acilis_suresi = 0.0
    SahteKamera.hata_ver.clear()
    monkeypatch.setattr(webcam.cv2, "VideoCapture", SahteKamera)
    monkeypatch.setattr(WebcamKaynagi, "YENIDEN_DENEME_SN", 0.1)


def test_durdurunca_cihaz_birakilir(monkeypatch):
    _hazirla(monkeypatch)
    k = WebcamKaynagi()
    k.baslat()
    assert _bekle(lambda: k.son_kare() is not None)
    k.durdur(bekle=True)
    assert SahteKamera.acik_olanlar == []


def test_okurken_hata_olursa_cihaz_birakilir_ve_yeniden_baglanir(monkeypatch):
    _hazirla(monkeypatch)
    k = WebcamKaynagi()
    k.baslat()
    assert _bekle(lambda: k.son_kare() is not None)
    ilk = SahteKamera.acik_olanlar[0]
    SahteKamera.hata_ver.set()
    assert _bekle(lambda: not ilk.bagli), "hatada eski bağlantı bırakılmalı"
    assert _bekle(lambda: len(SahteKamera.acik_olanlar) == 1 and SahteKamera.acik_olanlar[0] is not ilk)
    assert _bekle(lambda: k.son_kare() is not None)
    k.durdur(bekle=True)
    assert SahteKamera.acik_olanlar == []


def test_yavas_acilan_kamerada_hizli_kapat_ac_eski_baglanti_kalmaz(monkeypatch):
    _hazirla(monkeypatch)
    monkeypatch.setattr(webcam.threading.Thread, "join", lambda self, timeout=None: None)  # join beklemesin
    SahteKamera.acilis_suresi = 0.5
    k = WebcamKaynagi()
    k.baslat()
    time.sleep(0.1)          # ilk iş parçacığı hâlâ kamerayı açıyor
    k.durdur()
    SahteKamera.acilis_suresi = 0.0
    k.baslat()               # eski iş parçacığı bitmeden yeniden aç
    assert _bekle(lambda: k.son_kare() is not None)
    time.sleep(0.8)          # eski iş parçacığının açışı biter; kendi bayrağı kapalı olduğu için bırakmalı
    assert len(SahteKamera.acik_olanlar) == 1, "eski bağlantı arkada açık kalmamalı"
    k.durdur()
    assert _bekle(lambda: SahteKamera.acik_olanlar == [])
