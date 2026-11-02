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


def test_yazi_tasinir_ve_geri_al_eski_yerine_koyar():
    c = CizimDeposu()
    c.yazi_ekle("#FFFFFF", 0.1, 0.1, "Merhaba")
    s = c.anlik()[0][0]
    c.yazi_tasi(s, 0.5, 0.6)
    c.tasima_bitti(s, (0.1, 0.1))
    assert c.anlik()[0][0].noktalar[0] == (0.5, 0.6)
    assert c.geri_al()                                  # önce taşıma geri alınır
    assert c.anlik()[0][0].noktalar[0] == (0.1, 0.1)
    assert c.geri_al() and not c.anlik()[0]             # sonra yazının kendisi
    c.yazi_ekle("#FFFFFF", 0.1, 0.1, "x")
    c.yazi_tasi(c.anlik()[0][0], 2.0, -1.0)             # ekran dışına çıkmaz
    assert c.anlik()[0][0].noktalar[0] == (1.0, 0.0)


def _fare(tur, x, y, dugme=None):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    dugme = Qt.LeftButton if dugme is None else dugme
    basili = Qt.NoButton if tur == QMouseEvent.Type.MouseButtonRelease else dugme
    return QMouseEvent(tur, QPointF(x, y), QPointF(x, y), dugme, basili, Qt.NoModifier)


def test_bos_yazi_kutusu_disari_tiklayinca_kapanir_yeni_kutu_acilmaz(uygulama, tmp_path):
    from PySide6.QtGui import QMouseEvent
    d, k, depo, hat, cizimler, _ = _kur(tmp_path)
    k.calistir("kalem.ac_kapat")
    k.calistir("kalem.tur:5")
    katman = d.katman
    katman.mousePressEvent(_fare(QMouseEvent.Type.MouseButtonPress, 100, 100))
    assert katman._yazi_kutusu is not None
    katman.mousePressEvent(_fare(QMouseEvent.Type.MouseButtonPress, 400, 300))   # dışarı tık, hiç yazmadan
    assert katman._yazi_kutusu is None and not cizimler.anlik()[0]
    katman.mousePressEvent(_fare(QMouseEvent.Type.MouseButtonPress, 400, 300))   # sonraki tık yeni kutu açar
    assert katman._yazi_kutusu is not None
    katman._yazi_kutusu.setText("Selam")
    katman.mousePressEvent(_fare(QMouseEvent.Type.MouseButtonPress, 10, 10))      # yazılan kaydedilir
    assert katman._yazi_kutusu is None and cizimler.anlik()[0][0].metin == "Selam"
    k.calistir("kalem.kapat")


def test_yazi_suruklenerek_tasinir(uygulama, tmp_path):
    from PySide6.QtGui import QMouseEvent
    d, k, depo, hat, cizimler, _ = _kur(tmp_path)
    k.calistir("kalem.ac_kapat")
    k.calistir("kalem.tur:5")
    katman = d.katman
    W, H = katman.width(), katman.height()
    cizimler.yazi_ekle("#FFFFFF", 100 / W, 100 / H, "Buraya bak")
    katman.mousePressEvent(_fare(QMouseEvent.Type.MouseButtonPress, 110, 110))   # yazının üstüne bas
    assert katman._yazi_kutusu is None and katman._tasinan is not None
    katman.mouseMoveEvent(_fare(QMouseEvent.Type.MouseMove, 310, 210))
    katman.mouseReleaseEvent(_fare(QMouseEvent.Type.MouseButtonRelease, 310, 210))
    x, y = cizimler.anlik()[0][0].noktalar[0]
    assert abs(x * W - 300) < 1.5 and abs(y * H - 200) < 1.5
    assert cizimler.geri_al()
    x, y = cizimler.anlik()[0][0].noktalar[0]
    assert abs(x * W - 100) < 1.5 and abs(y * H - 100) < 1.5
    k.calistir("kalem.kapat")
