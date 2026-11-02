"""Birleşik bölge + kalem katmanı: kalem barı, araç/renk/kalınlık, silgi, bölge uygula/vazgeç."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from core.commands import KomutYoneticisi  # noqa: E402
from core.state import DurumDeposu  # noqa: E402
from overlay.drawing import RENKLER, CizimDeposu  # noqa: E402


@pytest.fixture(scope="module")
def uygulama():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _kur(tmp_path):
    from core.settings import Ayarlar
    from core.video_pipeline import VideoHatti
    from ui.drawing_overlay import KatmanDenetleyici

    class Kaynak:
        yontem = "sahte"

        def grab(self):
            return None

        def kapat(self):
            pass

    class Cikis:
        def kapat(self):
            pass

    depo, cizimler = DurumDeposu(), CizimDeposu()
    hat = VideoHatti(depo, Kaynak(), Cikis(), cizimler=cizimler)
    k = KomutYoneticisi()
    bildirimler = []
    d = KatmanDenetleyici(k, depo, hat, cizimler, None, Ayarlar(tmp_path / "s.json"), bildir=bildirimler.append)
    return d, k, depo, hat, cizimler, bildirimler


def test_kalem_bari_arac_renk_kalinlik(uygulama, tmp_path):
    d, k, depo, hat, cizimler, _ = _kur(tmp_path)
    k.calistir("kalem.ac_kapat")
    assert d.acik and depo.durum.kalem_acik and d.cubuk is not None
    assert len(d.cubuk.arac_dugmeleri) == 7 and len(d.cubuk.renk_dugmeleri) == 4
    assert d.renk == RENKLER[1]                                     # varsayılan kırmızı
    k.calistir("kalem.tur:7")
    k.calistir("kalem.renk:4")
    k.calistir("kalem.kalinlik:3")
    assert d.tur == "silgi" and d.renk == RENKLER[3] and d.kalinlik == "kalin"
    assert d.cubuk.arac_dugmeleri["silgi"].secili and d.cubuk.kalinlik_dugmeleri["kalin"].secili
    assert "Esc çık" in d.ipucu_satiri()
    k.calistir("kalem.kapat")
    assert not d.acik and d.katman is None and not depo.durum.kalem_acik


def test_silgi_sekli_siler_geri_al_geri_getirir():
    c = CizimDeposu()
    c.basla("kalem", "#EF4444", 0.1, 0.5, 1.8)
    c.surukle(0.9, 0.5)
    c.bitir()
    assert c.anlik()[0][0].carpan == 1.8
    c.basla("silgi", "", 0.5, 0.5)
    c.bitir()
    assert not c.anlik()[0]
    assert c.geri_al() and len(c.anlik()[0]) == 1


def test_bolge_uygula_mod_degistir_vazgec(uygulama, tmp_path):
    d, k, depo, hat, _, bildirimler = _kur(tmp_path)
    d.bolge_ac_kapat()
    assert d.katman is not None and d.katman.mod == "bolge" and d.cubuk is None
    d.katman.duzenleyici.oranlardan((0.25, 0.25, 0.5, 0.25))
    d.bolge_uygula(d.katman.duzenleyici.oranlar())
    assert hat.bolge.mod == "yakinlastir" and depo.durum.bolge == "yakinlastir"
    d.bolge_modu("vurgula")
    assert hat.bolge.mod == "vurgula" and d.ayarlar.al("region.mode") == "vurgula"
    d.bolge_vazgec()                                                  # Esc: önceki hâle (tam ekran)
    assert not hat.bolge.aktif and d.katman is None

    d.bolge_ac_kapat()
    d.katman.duzenleyici.oranlardan((0.1, 0.1, 0.3, 0.3))
    d.bolge_uygula(d.katman.duzenleyici.oranlar())
    d.bolge_tamam()
    assert hat.bolge.mod == "vurgula" and d.katman is None and bildirimler
    assert d.bolge_ac_kapat() == "Tam ekrana dönüldü" and not hat.bolge.aktif


def test_kalem_acikken_bolge_secip_kaleme_doner(uygulama, tmp_path):
    d, k, depo, hat, _, _ = _kur(tmp_path)
    k.calistir("kalem.ac_kapat")
    d.bolge_ac_kapat()
    assert d.katman.mod == "bolge" and d.cubuk is not None
    d.katman.duzenleyici.oranlardan((0.2, 0.2, 0.4, 0.4))
    d.bolge_uygula(d.katman.duzenleyici.oranlar())
    d.bolge_tamam()
    assert d.katman is not None and d.katman.mod == "kalem" and hat.bolge.aktif
    d.hepsini_kapat()
    assert d.katman is None and not hat.bolge.aktif
