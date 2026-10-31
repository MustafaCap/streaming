"""Ana pencere, mini çubuk ve kaynak seçici ekransız (offscreen) açılır; sade/gelişmiş görünüm ve
duraklat düğmesi doğru görünür."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from core.commands import KomutYoneticisi  # noqa: E402
from core.state import DurumDeposu  # noqa: E402


@pytest.fixture(scope="module")
def uygulama():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _hat():
    from core.video_pipeline import VideoHatti

    class Kaynak:
        yontem = "sahte"

        def grab(self):
            return None

        def kapat(self):
            pass

    class Cikis:
        def kapat(self):
            pass

    return VideoHatti(DurumDeposu(), Kaynak(), Cikis())


def _komutlar():
    k = KomutYoneticisi()
    for ad in ("cikis.ac_kapat", "kayit.ac_kapat", "kayit.duraklat", "kaynak.sec", "kamera.ac_kapat",
               "ses.mikrofon", "ses.sistem", "bolge.sec", "kalem.ac_kapat", "panik"):
        k.kaydet(ad, ad, lambda _: None)
    return k


def test_ana_pencere_sade_acilir_gelismis_acilip_kapanir(uygulama, tmp_path):
    from core.settings import Ayarlar
    from ui.main_window import AnaPencere
    ayarlar = Ayarlar(tmp_path / "s.json")
    depo = DurumDeposu()
    p = AnaPencere(depo, _komutlar(), _hat(), ayarlar=ayarlar)
    p.show()
    assert not p.sol_panel.isVisible() and not p.bilgi.isVisible()
    assert not p.kontroller["kayit.duraklat"].isVisible()
    assert p.kontroller["kaynak.sec"].text().splitlines()[1] == "Tüm ekran"
    p.gelismis_dugmesi.setChecked(True)
    assert p.sol_panel.isVisible() and ayarlar.al("ui.advanced") is True

    depo.guncelle(kayit="açık", kayit_suresi=65)
    p._durumu_goster(depo.durum)
    assert p.kontroller["kayit.duraklat"].isVisible()
    depo.guncelle(kayit_duraklatildi=True)
    p._durumu_goster(depo.durum)
    assert "duraklatıldı" in p.rozet_kayit.text() and "Devam et" in p.kontroller["kayit.duraklat"].text()

    depo.guncelle(kaynak_turu="pencere", kaynak_adi="Çok uzun bir pencere başlığı - Microsoft Edge")
    p._durumu_goster(depo.durum)
    assert p.kontroller["kaynak.sec"].text().splitlines()[1].endswith("…")
    p.tepsiye_kucul = False
    p.close()


def test_mini_cubukta_duraklat_sadece_kayitta(uygulama):
    from ui.mini_bar import MiniCubuk
    depo = DurumDeposu()
    m = MiniCubuk(_komutlar(), _hat(), None)
    m.show()
    m.durumu_goster(depo.durum)
    assert m.dugmeler["kayit.duraklat"].isHidden()
    depo.guncelle(kayit="açık", kayit_duraklatildi=True)
    m.durumu_goster(depo.durum)
    assert not m.dugmeler["kayit.duraklat"].isHidden() and m.dugmeler["kayit.duraklat"].text() == "▶"
    m.close()


def test_kaynak_secici_ilk_satir_tum_ekran(uygulama):
    from ui.pencere_secici import PencereSecici
    s = PencereSecici(listele=lambda: [(42, "Not Defteri", "notepad.exe")])
    assert s.liste.count() == 2 and not s.bos.isVisible()
    s._sec()
    assert s.secilen == "ekran"
    s.liste.setCurrentRow(1)
    s._sec()
    assert s.secilen == (42, "Not Defteri")
