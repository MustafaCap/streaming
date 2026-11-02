import pytest

from core.commands import KomutYoneticisi
from core.hotkeys import (MOD_CONTROL, MOD_SHIFT, VARSAYILAN_KISAYOLLAR, GecersizTus, gruplara_ayir,
                          tus_coz, tus_metni)


@pytest.mark.parametrize("metin,beklenen", [
    ("F6", (0, 0x75)), ("Ctrl+F12", (MOD_CONTROL, 0x7B)), ("Ctrl+1", (MOD_CONTROL, 0x31)),
    ("Ctrl+Shift+R", (MOD_CONTROL | MOD_SHIFT, 0x52)), ("ctrl + z", (MOD_CONTROL, 0x5A)),
    ("Del", (0, 0x2E)), ("1", (0, 0x31)), ("Num5", (0, 0x65)),
])
def test_tus_coz(metin, beklenen):
    assert tus_coz(metin) == beklenen


@pytest.mark.parametrize("metin", ["", "Ctrl+", "Hyper+A", "F25", "Ğ", "Ctrl+Bilinmeyen", "F12"])
def test_gecersiz_tuslar(metin):
    with pytest.raises(GecersizTus):
        tus_coz(metin)


def test_varsayilanlarin_hepsi_cozulur():
    for tus in VARSAYILAN_KISAYOLLAR.values():
        tus_coz(tus)


def test_gruplara_ayir_olmayan_komutu_ve_cakismayi_atlar():
    k = KomutYoneticisi()
    k.kaydet("ses.mikrofon", "Mikrofon", lambda _: None)
    k.kaydet("sahne.sec", "Sahne", lambda _: None)
    sonuc = gruplara_ayir({"ses.mikrofon": "f8", "sahne.sec:1": "Ctrl+1", "panik": "F12",
                           "sahne.sec:2": "ctrl+1", "bas_konus": ""}, k)
    assert sonuc == {"F8": "ses.mikrofon", "Ctrl+1": "sahne.sec:1"}
    assert tus_metni("ctrl+shift+r") == "Ctrl+Shift+R"


def test_bas_konus_tus_durumunu_izler():
    import time
    basili = set()
    olaylar = []
    bk = __import__("core.hotkeys", fromlist=["BasKonus"]).BasKonus(olaylar.append, lambda vk: vk in basili)
    assert bk.ayarla("Ctrl+Space") and bk.aktif
    basili.add(0x20)            # Ctrl olmadan Space: sayılmaz
    time.sleep(0.1)
    assert olaylar == []
    basili.add(0x11)
    time.sleep(0.1)
    basili.clear()
    time.sleep(0.1)
    assert olaylar == [True, False]
    assert not bk.ayarla("Hyper+X") and not bk.aktif


def test_fare_tuslari_cozulur_sol_sag_tik_olmaz():
    from core.hotkeys import FARE_TUSLARI, fare_tusu_mu, tus_coz, tus_metni
    assert tus_coz("Fare4") == (0, FARE_TUSLARI["fare4"])
    assert tus_coz("Ctrl+Shift+Fare5") == (MOD_CONTROL | MOD_SHIFT, FARE_TUSLARI["fare5"])
    assert tus_metni("ctrl+fare3") == "Ctrl+Fare3"
    assert fare_tusu_mu("Alt+Fare4") and not fare_tusu_mu("F4")
    for tus in ("Fare1", "Ctrl+Fare2"):
        with pytest.raises(GecersizTus):
            tus_coz(tus)


def test_fare_kisayolu_basinca_bir_kez_ve_degistiriciyle_tam_eslesir():
    from core.hotkeys import KisayolYoneticisi
    calisan = []
    y = KisayolYoneticisi(calisan.append)
    y.fare_grubu_ayarla("genel", {("genel", "Fare4"): (0, 0x05, "ses.mikrofon"),
                                  ("genel", "Ctrl+Fare4"): (MOD_CONTROL, 0x05, "kamera.ac_kapat")})
    basili = set()
    oku = basili.__contains__
    y.fare_yokla(oku)
    assert calisan == []
    basili.add(0x05)
    y.fare_yokla(oku)
    y.fare_yokla(oku)                               # basılı tutmak tekrar tetiklemez
    assert calisan == ["ses.mikrofon"]
    basili.clear()
    y.fare_yokla(oku)
    basili.update({0x11, 0x05})                     # Ctrl + Fare4: sadece Ctrl'li olan
    y.fare_yokla(oku)
    assert calisan == ["ses.mikrofon", "kamera.ac_kapat"]
    basili.clear()
    y.fare_yokla(oku)
    y.fare_grubu_ayarla("genel", {})                # grup kaldırılınca çalışmaz
    basili.add(0x05)
    y.fare_yokla(oku)
    assert calisan == ["ses.mikrofon", "kamera.ac_kapat"]


def test_ayarlarda_fare_tusu_hucreye_yazilir():
    QtCore = pytest.importorskip("PySide6.QtCore")
    from ui.settings_dialog import fare_kisayolu
    Qt = QtCore.Qt
    assert fare_kisayolu(Qt.BackButton, Qt.NoModifier) == "Fare4"
    assert fare_kisayolu(Qt.MiddleButton, Qt.ControlModifier | Qt.ShiftModifier) == "Ctrl+Shift+Fare3"
    assert fare_kisayolu(Qt.LeftButton, Qt.NoModifier) == ""
