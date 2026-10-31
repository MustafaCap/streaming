"""Hatalar kaybolmasın: arka plan iş parçacığı hataları log'a, tekrarlayan hata seyrek yazılsın."""

import logging
import threading

from core import logging_setup
from core.logging_setup import SeyrekHata


def test_arka_plan_hatasi_loga_yazilir(caplog):
    eski_thread, eski_sys = threading.excepthook, __import__("sys").excepthook
    try:
        logging_setup.kur()
        caplog.set_level(logging.ERROR)
        logging.getLogger().addHandler(caplog.handler)

        def patla():
            raise ValueError("webcam döngüsü bozuldu")

        t = threading.Thread(target=patla, name="webcam")
        t.start()
        t.join()
        assert any("webcam" in r.getMessage() and r.exc_info and "bozuldu" in str(r.exc_info[1])
                   for r in caplog.records)
    finally:
        threading.excepthook, __import__("sys").excepthook = eski_thread, eski_sys
        for h in logging.getLogger().handlers:
            h.close()
        logging.getLogger().handlers.clear()
        import faulthandler
        faulthandler.disable()
        if logging_setup._cokme_dosyasi is not None:   # Windows'ta açık dosya geçici klasörü kilitlemesin
            logging_setup._cokme_dosyasi.close()
            logging_setup._cokme_dosyasi = None


def test_ayni_hata_seyrek_yazilir(caplog):
    log = logging.getLogger("deneme.seyrek")
    caplog.set_level(logging.ERROR, logger="deneme.seyrek")
    seyrek = SeyrekHata(log, aralik_sn=3600)
    for _ in range(100):
        try:
            raise RuntimeError("aynı hata")
        except RuntimeError:
            seyrek.yaz("Video hattında hata")
    kayitlar = [r for r in caplog.records if r.name == "deneme.seyrek"]
    assert len(kayitlar) == 1 and kayitlar[0].exc_info is not None


def test_seyrek_hata_sure_dolunca_ozet_yazar(caplog, monkeypatch):
    log = logging.getLogger("deneme.ozet")
    caplog.set_level(logging.ERROR, logger="deneme.ozet")
    simdi = [100.0]
    monkeypatch.setattr(logging_setup.time, "monotonic", lambda: simdi[0])
    seyrek = SeyrekHata(log, aralik_sn=30)
    hata = RuntimeError("x")
    for _ in range(5):
        seyrek.yaz("Hata", hata)
    simdi[0] += 31
    seyrek.yaz("Hata", hata)
    mesajlar = [r.getMessage() for r in caplog.records if r.name == "deneme.ozet"]
    assert len(mesajlar) == 2 and "5 kez daha" in mesajlar[1]
