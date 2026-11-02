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
    k = p.kontrol
    assert p.sol_panel.isVisible()                    # 2.0.1: ilk açılışta Gelişmiş açık
    p.gelismis_dugmesi.setChecked(False)
    assert not p.sol_panel.isVisible() and ayarlar.al("ui.advanced") is False
    cikildi = []
    p.uygulamadan_cik = lambda: cikildi.append(1)
    p.cikis_dugmesi.click()                           # Çıkış alt satırda, CPU yazısının yanında
    assert cikildi == [1] and p.cikis_dugmesi.isVisible()
    assert k.kayit.isVisible() and not k.kayit_grubu.isVisible()
    assert p.goster.secili == "Ekran 1"
    p.gelismis_dugmesi.setChecked(True)
    assert p.sol_panel.isVisible() and ayarlar.al("ui.advanced") is True
    assert p.minimumWidth() > 760

    depo.guncelle(kayit="açık", kayit_suresi=65, mikrofon_sessiz=True)
    p._durumu_goster(depo.durum)
    assert not k.kayit.isVisible() and k.kayit_grubu.isVisible()
    assert k.kayit_grubu.sure.text() == "01:05"
    assert k.mikrofon.kapali and k.mikrofon.metin == "Sessizde"
    assert k.kayit_grubu.duraklat.accessibleName() == "Kaydı duraklat"
    depo.guncelle(kayit_duraklatildi=True)
    p._durumu_goster(depo.durum)
    assert k.kayit_grubu.duraklat.accessibleName() == "Kayda devam et"
    assert k.kayit_grubu.nokta.renk != "#e5484d"     # duraklatınca nokta gri

    depo.guncelle(kaynak_turu="pencere", kaynak_adi="Çok uzun bir pencere başlığı - Microsoft Edge")
    p._durumu_goster(depo.durum)
    assert p.goster.secili.endswith("…")
    depo.guncelle(bolge="yakinlastir")
    p._durumu_goster(depo.durum)
    assert p.goster.secili == "Seçili bölge" and k.bolge.secili
    p.tepsiye_kucul = False
    p.close()


def test_dar_pencerede_sutunlar_alt_alta(uygulama, tmp_path):
    from core.settings import Ayarlar
    from ui.main_window import AnaPencere
    ayarlar = Ayarlar(tmp_path / "s.json")
    ayarlar.ayarla("ui.advanced", True)
    p = AnaPencere(DurumDeposu(), _komutlar(), _hat(), ayarlar=ayarlar)
    p.resize(1320, 800)
    p.show()
    uygulama.processEvents()
    assert p._duzen == "genis"
    p.resize(920, 700)
    uygulama.processEvents()
    assert p._duzen in ("dar", "cok_dar")
    p.tepsiye_kucul = False
    p.close()


def test_sahne_ekle_yeniden_adlandir_sil(uygulama):
    from ui.sahne_panelleri import SahnelerPaneli
    hat = _hat()
    k = KomutYoneticisi()
    k.kaydet("sahne.sec", "", lambda p: hat.sahne_sec(int(p) - 1) and None)
    panel = SahnelerPaneli(hat, k, lambda komut: "")
    once = len(hat.sahneler.sahneler)
    panel.sahne_ekle()
    assert len(hat.sahneler.sahneler) == once + 1
    assert hat.sahneler.aktif.ad == "Yeni sahne 1" and hat.sahneler.indeks == once
    assert panel.satirlar[-1].secili
    panel.satirlar[-1].yeniden_adlandirildi.emit("Sunum")
    assert hat.sahneler.aktif.ad == "Sunum"
    panel._sil(once)
    assert len(hat.sahneler.sahneler) == once


def test_kaynak_gizle_kaldir_ekle(uygulama):
    from ui.sahne_panelleri import KaynaklarPaneli
    hat = _hat()
    panel = KaynaklarPaneli(hat, None, lambda: None, lambda geri: None)
    ilk = hat.sahneler.aktif.kaynaklar[0]
    panel.satirlar[0].goz.click()
    assert not hat.sahneler.aktif.kaynaklar[0].gorunur
    assert panel.satirlar[0].goz.accessibleName().endswith("gizli, göster")
    panel._ekle("metin", text="Mustafa")
    assert hat.sahneler.aktif.kaynaklar[0].tur == "metin" and panel.satirlar[0].bilgi.text() == "Mustafa"
    panel.satirlar[0].kaldir.click()
    assert hat.sahneler.aktif.kaynaklar[0].kimlik == ilk.kimlik


def test_ses_modlari_ve_kaydet_baglantisi(uygulama, tmp_path):
    from core.audio_mixer import SesKaristirici
    from core.settings import Ayarlar
    from ui.mixer_panel import MikserPaneli
    ayarlar = Ayarlar(tmp_path / "s.json")
    m = SesKaristirici()
    m.kanal_ekle("mikrofon", "M", 0.8, False)
    m.kanal_ekle("sistem", "S", 0.8, False)
    panel = MikserPaneli(DurumDeposu(), None, None, m, ayarlar)
    assert panel.modlar.secili == 1 and panel.kaydet_dugmesi.isHidden()   # 80/80 = Dengeli
    panel.modlar._tikla(0)                                                # Sesim
    assert round(m.kanallar["sistem"].kazanc * 100) == 45 and ayarlar.al("audio.last_mode") == "sesim"
    panel.mik.surgu.setValue(90)                                          # elle değişti
    assert panel.modlar.secili == -1 and not panel.kaydet_dugmesi.isHidden()
    assert panel.kaydet_dugmesi.text() == "Sesim'e kaydet"
    panel.kaydet_dugmesi.click()
    assert ayarlar.al("audio.modes")["sesim"] == [90, 45] and panel.modlar.secili == 0


def test_mini_bar_genis_acilir_kayitta_kuculur(uygulama):
    from ui.mini_bar import MiniCubuk
    depo = DurumDeposu()
    hat = _hat()
    m = MiniCubuk(_komutlar(), hat, None)
    m.durumu_goster(depo.durum)
    m.goster()
    assert m.genis and not m._araclar.isHidden() and not m.kayit.isHidden() and m.kayit_grubu.isHidden()
    assert hat.mini_gorunur
    depo.guncelle(kayit="açık", kayit_suresi=261, mikrofon_sessiz=True)
    m.durumu_goster(depo.durum)
    assert not m.genis and m._araclar.isHidden() and not m.kayit_grubu.isHidden()
    assert m.kayit_grubu.sure.text() == "04:21" and m.kayit_grubu.bitir.isHidden()
    m.genislet(True)
    assert not m._araclar.isHidden() and not m.kayit_grubu.bitir.isHidden()
    assert m.dugmeler["ses.mikrofon"].kapali and m.dugmeler["ses.mikrofon"].accessibleName() == "Mikrofon kapalı, aç"
    depo.guncelle(kayit_duraklatildi=True)
    m.durumu_goster(depo.durum)
    assert m.kayit_grubu.duraklat.accessibleName() == "Kayda devam et"
    m.close()
    assert not hat.mini_gorunur


def test_kaynak_secici_ilk_satir_tum_ekran(uygulama):
    from ui.pencere_secici import PencereSecici
    s = PencereSecici(listele=lambda: [(42, "Not Defteri", "notepad.exe")])
    assert "🖥" not in s.liste.item(0).text()
    assert s.liste.count() == 2 and not s.bos.isVisible()
    s._sec()
    assert s.secilen == "ekran"
    s.liste.setCurrentRow(1)
    s._sec()
    assert s.secilen == (42, "Not Defteri")


def test_mini_bar_sahnede_kamera_yoksa_kamera_dugmesi_kapali_ve_basilamaz(uygulama):
    from scenes.scene_manager import Sahne, SahneYoneticisi
    from ui.mini_bar import MiniCubuk
    hat = _hat()
    hat.kamera = object()                                  # takılı bir webcam varmış gibi
    hat.sahneler = SahneYoneticisi([Sahne("Ekran + kamera", ekran=True, kamera="corner"),
                                    Sahne("Sadece ekran", ekran=True)], gecis_ms=0)
    hat.kamerayi_ayarla(True)
    depo = DurumDeposu()
    m = MiniCubuk(_komutlar(), hat, None)
    m.durumu_goster(depo.durum)
    kamera = m.dugmeler["kamera.ac_kapat"]
    assert kamera.isEnabled() and not kamera.kapali
    hat.sahne_sec(1)
    m.durumu_goster(depo.durum)
    assert not kamera.isEnabled() and kamera.kapali and kamera.accessibleName() == "Bu sahnede kamera yok"
    m.close()
