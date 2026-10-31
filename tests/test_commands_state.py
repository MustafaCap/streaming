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
