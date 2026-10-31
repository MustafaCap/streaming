import pytest

from core.commands import KomutYoneticisi
from core.state import DurumDeposu


def test_komut_calisir_ve_dinleyiciye_haber_verir():
    k = KomutYoneticisi()
    gelen = []
    k.kaydet("sahne.sec", "Sahne seç", lambda p: f"Sahne {p}")
    k.dinle(lambda ad, mesaj: gelen.append((ad, mesaj)))
    assert k.calistir("sahne.sec:2")
    assert gelen == [("sahne.sec:2", "Sahne 2")]


def test_bilinmeyen_ve_hatali_komut_cokertmez():
    k = KomutYoneticisi()
    k.kaydet("bozuk", "Bozuk", lambda p: 1 / 0)
    assert not k.calistir("yok")
    assert not k.calistir("bozuk")


def test_ayni_komut_iki_kez_kaydedilemez():
    k = KomutYoneticisi()
    k.kaydet("a", "A", lambda p: None)
    with pytest.raises(ValueError):
        k.kaydet("a", "A", lambda p: None)


def test_durum_degisince_dinleyici_cagrilir_degismezse_cagrilmaz():
    d = DurumDeposu()
    olaylar = []
    d.dinle(lambda eski, yeni: olaylar.append((eski.cikis_acik, yeni.cikis_acik)))
    d.guncelle(cikis_acik=True)
    d.guncelle(cikis_acik=True)
    assert olaylar == [(False, True)]


def test_bilinmeyen_durum_alani_reddedilir():
    with pytest.raises(KeyError):
        DurumDeposu().guncelle(boyle_bir_alan=1)


def test_kayit_yayin_kapaliyken_kamerasiz_baslar_bitince_kamera_geri_gelir():
    from core.settings import Ayarlar
    from main import komutlari_kaydet

    class Hat:
        cikis_istegi, kamera_istegi, kamera = False, True, object()

        def kamerayi_ayarla(self, acik):
            self.kamera_istegi = acik

    class Kayitci:
        kayitta, klasor, son_hata = False, "Videolar", ""

        def baslat(self):
            self.kayitta = True
            return True

        def durdur(self, bitti):
            self.kayitta = False

    k, depo, hat = KomutYoneticisi(), DurumDeposu(), Hat()
    komutlari_kaydet(k, depo, hat, ayarlar=Ayarlar(), kayitci=Kayitci())
    mesajlar = []
    k.dinle(lambda ad, mesaj: mesajlar.append(mesaj))
    assert k.calistir("kayit.ac_kapat") and "kamerasız" in mesajlar[-1]
    assert depo.durum.kayit == "açık" and hat.kamera_istegi is False
    k.calistir("kayit.ac_kapat")
    assert hat.kamera_istegi is True

    hat.cikis_istegi = True                       # yayındayken karşı tarafın görüntüsü değişmez
    k.calistir("kayit.ac_kapat")
    assert hat.kamera_istegi is True


def test_kapanis_takilirsa_surec_zorla_kapanir():
    import threading as th

    import main
    cagrildi = th.Event()
    zamanlayici = main.kapanis_bekcisi(0.05, cik=lambda kod: cagrildi.set())
    assert cagrildi.wait(2), "kapanış bekçisi süre dolunca süreci kapatmalı"
    zamanlayici.cancel()


def test_kayit_duraklat_devam_et_komutu():
    from main import komutlari_kaydet

    class Hat:
        cikis_istegi, kamera_istegi, kamera = True, False, None

    class Kayitci:
        kayitta, duraklatildi, klasor, son_hata = False, False, "Videolar", ""

        def baslat(self):
            self.kayitta = True
            return True

        def durdur(self, bitti):
            self.kayitta = self.duraklatildi = False

        def duraklat(self):
            self.duraklatildi = True
            return True

        def devam_et(self):
            self.duraklatildi = False
            return True

    k, depo, kayitci = KomutYoneticisi(), DurumDeposu(), Kayitci()
    komutlari_kaydet(k, depo, Hat(), kayitci=kayitci)
    mesajlar = []
    k.dinle(lambda ad, mesaj: mesajlar.append(mesaj))
    k.calistir("kayit.duraklat")
    assert "açık değil" in mesajlar[-1] and not depo.durum.kayit_duraklatildi
    k.calistir("kayit.ac_kapat")
    k.calistir("kayit.duraklat")
    assert kayitci.duraklatildi and depo.durum.kayit_duraklatildi and "duraklatıldı" in mesajlar[-1]
    k.calistir("kayit.duraklat")
    assert not kayitci.duraklatildi and not depo.durum.kayit_duraklatildi
    k.calistir("kayit.duraklat")
    k.calistir("kayit.ac_kapat")                  # duraklatılmışken durdur
    assert not kayitci.kayitta and not depo.durum.kayit_duraklatildi
